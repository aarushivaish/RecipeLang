import re, sys

# ═══════════════════════════════════════════════
# STAGE 1: LEXER
# ═══════════════════════════════════════════════

KEYWORDS = {
    'RECIPE', 'SERVES', 'INGREDIENT', 'STEP',
    'BAKE', 'FOR', 'MIX', 'SCALE', 'TO', 'SERVE',
    'PREP', 'COOK', 'ASSEMBLE', 'CONVERT',
    'ALLERGEN', 'DIET', 'CONTAINS', 'CLASSIFY'
}

UNITS      = {'g', 'kg', 'ml', 'l', 'tsp', 'tbsp'}
TEMP_UNITS = {'C', 'F'}
TIME_UNITS = {'min', 'hr'}

KNOWN_ALLERGENS = {
    'milk', 'nuts', 'gluten', 'eggs', 'soy',
    'wheat', 'fish', 'shellfish', 'peanuts', 'sesame'
}

KNOWN_DIETS = {
    'vegan', 'vegetarian', 'gluten-free',
    'dairy-free', 'nut-free', 'halal', 'kosher'
}

DIET_CONFLICTS = {
    'vegan':       {'milk', 'eggs', 'fish', 'shellfish'},
    'vegetarian':  {'fish', 'shellfish'},
    'gluten-free': {'gluten', 'wheat'},
    'dairy-free':  {'milk'},
    'nut-free':    {'nuts', 'peanuts'},
}

INGREDIENT_ALLERGEN_MAP = {
    'flour':   'gluten',
    'milk':    'milk',
    'butter':  'milk',
    'cream':   'milk',
    'cheese':  'milk',
    'eggs':    'eggs',
    'egg':     'eggs',
    'soy':     'soy',
    'tofu':    'soy',
    'peanuts': 'peanuts',
    'nuts':    'nuts',
    'almond':  'nuts',
    'walnut':  'nuts',
    'wheat':   'wheat',
    'fish':    'fish',
    'shrimp':  'shellfish',
    'sesame':  'sesame',
}

UNIT_CONVERSIONS = {
    'g':    ('g',   1),
    'kg':   ('g',   1000),
    'ml':   ('ml',  1),
    'l':    ('ml',  1000),
    'tsp':  ('tsp', 1),
    'tbsp': ('tsp', 3),
}

UNIT_UPGRADE = {
    'g':   (1000, 'kg',   0.001),
    'ml':  (1000, 'l',    0.001),
    'tsp': (3,    'tbsp', 1/3),
}

TOKEN_PATTERNS = [
    ('NUMBER',  r'\d+(\.\d+)?'),
    ('STRING',  r'"[^"]*"'),
    ('NAME',    r'[A-Za-z][A-Za-z0-9_-]*'),
    ('COMMENT', r'#[^\n]*'),
    ('NEWLINE', r'\n'),
    ('SKIP',    r'[ \t]+'),
]

def tokenize(source):
    tokens = []
    line   = 1
    pattern = '|'.join(f'(?P<{n}>{p})' for n, p in TOKEN_PATTERNS)
    for m in re.finditer(pattern, source):
        kind = m.lastgroup
        val  = m.group()
        if kind in ('SKIP', 'COMMENT'):
            pass
        elif kind == 'NEWLINE':
            line += 1
        elif kind == 'NAME' and val in KEYWORDS:
            tokens.append(('KEYWORD', val, line))
        elif kind == 'NAME' and val in UNITS | TEMP_UNITS | TIME_UNITS:
            tokens.append(('UNIT', val, line))
        else:
            tokens.append((kind, val, line))
    tokens.append(('EOF', '', line))
    return tokens

# ═══════════════════════════════════════════════
# STAGE 2: PARSER
# ═══════════════════════════════════════════════

SECTION_KEYWORDS = {'PREP', 'COOK', 'ASSEMBLE', 'SERVE'}

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos    = 0

    def peek(self):
        return self.tokens[self.pos]

    def consume(self, kind=None, val=None):
        tok = self.tokens[self.pos]
        if kind and tok[0] != kind:
            raise SyntaxError(
                f"Line {tok[2]}: expected {kind}, got {tok[0]} ({tok[1]!r})"
            )
        if val and tok[1] != val:
            raise SyntaxError(
                f"Line {tok[2]}: expected '{val}', got {tok[1]!r}"
            )
        self.pos += 1
        return tok

    def parse(self):
        node = {'type': 'RECIPE'}

        # RECIPE "name"
        self.consume('KEYWORD', 'RECIPE')
        node['name'] = self.consume('STRING')[1].strip('"')

        # SERVES n
        self.consume('KEYWORD', 'SERVES')
        node['serves'] = float(self.consume('NUMBER')[1])

        # INGREDIENT blocks
        node['ingredients'] = []
        while self.peek()[1] == 'INGREDIENT':
            node['ingredients'].append(self.parse_ingredient())

        # ALLERGEN CONTAINS milk eggs gluten ...
        node['allergens'] = []
        if self.peek()[1] == 'ALLERGEN':
            self.consume('KEYWORD', 'ALLERGEN')
            self.consume('KEYWORD', 'CONTAINS')
            while self.peek()[0] == 'NAME':
                node['allergens'].append(self.consume('NAME')[1])

        # DIET CLASSIFY vegan vegetarian ...
        node['diets'] = []
        if self.peek()[1] == 'DIET':
            self.consume('KEYWORD', 'DIET')
            self.consume('KEYWORD', 'CLASSIFY')
            while self.peek()[0] == 'NAME':
                node['diets'].append(self.consume('NAME')[1])

        # PREP / COOK / ASSEMBLE / SERVE sections
        node['sections'] = []
        while self.peek()[0] != 'EOF' and self.peek()[1] != 'SCALE':
            if self.peek()[1] in SECTION_KEYWORDS:
                node['sections'].append(self.parse_section())
            else:
                raise SyntaxError(
                    f"Line {self.peek()[2]}: expected a section "
                    f"(PREP/COOK/ASSEMBLE/SERVE), got {self.peek()[1]!r}"
                )

        # Optional SCALE TO n
        node['scale_to'] = None
        if self.peek()[1] == 'SCALE':
            self.consume('KEYWORD', 'SCALE')
            self.consume('KEYWORD', 'TO')
            node['scale_to'] = float(self.consume('NUMBER')[1])

        return node

    def parse_ingredient(self):
        self.consume('KEYWORD', 'INGREDIENT')
        name   = self.consume('NAME')[1]
        amount = float(self.consume('NUMBER')[1])
        unit   = self.consume('UNIT')[1] if self.peek()[0] == 'UNIT' else ''
        return {'type': 'INGREDIENT', 'name': name, 'amount': amount, 'unit': unit}

    def parse_section(self):
        section_name = self.consume('KEYWORD')[1]
        statements   = []
        while (self.peek()[0] != 'EOF'
               and self.peek()[1] not in SECTION_KEYWORDS
               and self.peek()[1] != 'SCALE'):
            statements.append(self.parse_statement())
        return {'type': 'SECTION', 'name': section_name, 'statements': statements}

    def parse_statement(self):
        tok = self.peek()

        if tok[1] == 'STEP':
            self.consume('KEYWORD', 'STEP')
            text = self.consume('STRING')[1].strip('"')
            return {'type': 'STEP', 'text': text}

        elif tok[1] == 'BAKE':
            self.consume('KEYWORD', 'BAKE')
            temp      = float(self.consume('NUMBER')[1])
            temp_unit = self.consume('UNIT')[1]
            self.consume('KEYWORD', 'FOR')
            duration  = float(self.consume('NUMBER')[1])
            time_unit = self.consume('UNIT')[1]
            return {
                'type': 'BAKE',
                'temp': temp, 'temp_unit': temp_unit,
                'duration': duration, 'time_unit': time_unit
            }

        elif tok[1] == 'MIX':
            self.consume('KEYWORD', 'MIX')
            names = []
            while self.peek()[0] == 'NAME':
                names.append(self.consume('NAME')[1])
            return {'type': 'MIX', 'ingredients': names}

        elif tok[1] == 'CONVERT':
            self.consume('KEYWORD', 'CONVERT')
            name        = self.consume('NAME')[1]
            self.consume('KEYWORD', 'TO')
            target_unit = self.consume('UNIT')[1]
            return {'type': 'CONVERT', 'ingredient': name, 'to_unit': target_unit}

        else:
            raise SyntaxError(f"Line {tok[2]}: unexpected token {tok[1]!r}")

# ═══════════════════════════════════════════════
# STAGE 3: SEMANTIC ANALYSER
# ═══════════════════════════════════════════════

COMPATIBLE_UNITS = {
    frozenset({'g',   'kg'}),
    frozenset({'ml',  'l'}),
    frozenset({'tsp', 'tbsp'}),
}

def units_compatible(u1, u2):
    if u1 == u2:
        return True
    for group in COMPATIBLE_UNITS:
        if u1 in group and u2 in group:
            return True
    return False

def infer_allergens(ingredients):
    inferred = set()
    for ing in ingredients:
        key = ing['name'].lower()
        if key in INGREDIENT_ALLERGEN_MAP:
            inferred.add(INGREDIENT_ALLERGEN_MAP[key])
    return inferred

def analyse(ast):
    errors   = []
    warnings = []
    declared = {ing['name']: ing for ing in ast['ingredients']}

    # ── Basic checks ──────────────────────────
    if ast['serves'] <= 0:
        errors.append("SERVES must be a positive number")

    if not ast['sections']:
        errors.append("Recipe must have at least one section (PREP/COOK/ASSEMBLE/SERVE)")

    # ── Allergen checks ───────────────────────
    declared_allergens = set(ast['allergens'])
    inferred_allergens = infer_allergens(ast['ingredients'])

    for allergen in declared_allergens:
        if allergen not in KNOWN_ALLERGENS:
            errors.append(
                f"Unknown allergen '{allergen}'. "
                f"Known allergens: {', '.join(sorted(KNOWN_ALLERGENS))}"
            )

    # Warn about allergens implied by ingredients but not declared
    for missing in sorted(inferred_allergens - declared_allergens):
        warnings.append(
            f"Ingredient implies allergen '{missing}' "
            f"but it is not declared under ALLERGEN CONTAINS"
        )

    # ── Diet checks ───────────────────────────
    all_allergens = declared_allergens | inferred_allergens
    for diet in ast['diets']:
        if diet not in KNOWN_DIETS:
            errors.append(
                f"Unknown diet '{diet}'. "
                f"Known diets: {', '.join(sorted(KNOWN_DIETS))}"
            )
        elif diet in DIET_CONFLICTS:
            conflicts = DIET_CONFLICTS[diet] & all_allergens
            if conflicts:
                errors.append(
                    f"DIET '{diet}' conflicts with allergen(s): "
                    f"{', '.join(sorted(conflicts))}. "
                    f"Remove the conflicting ingredients or correct the DIET tag."
                )

    # ── Section statement checks ───────────────
    for section in ast['sections']:
        for stmt in section['statements']:
            if stmt['type'] == 'BAKE':
                if stmt['temp'] <= 0:
                    errors.append("BAKE temperature must be > 0")
                if stmt['duration'] <= 0:
                    errors.append("BAKE duration must be > 0")

            elif stmt['type'] == 'MIX':
                for name in stmt['ingredients']:
                    if name not in declared:
                        errors.append(f"MIX uses undeclared ingredient: '{name}'")

            elif stmt['type'] == 'CONVERT':
                name = stmt['ingredient']
                if name not in declared:
                    errors.append(f"CONVERT references undeclared ingredient: '{name}'")
                else:
                    cur = declared[name]['unit']
                    tgt = stmt['to_unit']
                    if not units_compatible(cur, tgt):
                        errors.append(
                            f"CONVERT: cannot convert '{name}' "
                            f"from '{cur}' to '{tgt}' — incompatible units"
                        )

    if ast['scale_to'] is not None and ast['scale_to'] <= 0:
        errors.append("SCALE TO value must be positive")

    # ── Report ────────────────────────────────
    for w in warnings:
        print(f"  [WARN]  {w}")

    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        sys.exit(1)

    print(f"  [OK] {len(declared)} ingredients, {len(ast['sections'])} sections")
    print(f"  [OK] Allergens : {', '.join(sorted(all_allergens)) or 'none detected'}")
    print(f"  [OK] Diet tags : {', '.join(ast['diets']) or 'none declared'}")
    return ast

# ═══════════════════════════════════════════════
# STAGE 4: CODE GENERATOR
# ═══════════════════════════════════════════════

def generate(ast):
    lines = []
    inferred      = infer_allergens(ast['ingredients'])
    all_allergens = sorted(set(ast['allergens']) | inferred)

    lines.append('# Generated by RecipeLang compiler')
    lines.append('')

    # ── Ingredient table ──
    lines.append('ingredients = {')
    for ing in ast['ingredients']:
        lines.append(
            f'    "{ing["name"]}": '
            f'{{"amount": {ing["amount"]}, "unit": "{ing["unit"]}"}},')
    lines.append('}')
    lines.append('')

    lines.append(f'recipe_name = "{ast["name"]}"')
    lines.append(f'serves      = {ast["serves"]}')
    lines.append(f'allergens   = {all_allergens}')
    lines.append(f'diets       = {ast["diets"]}')
    lines.append('')

    # ── SCALE ──
    if ast['scale_to']:
        factor = ast['scale_to'] / ast['serves']
        lines.append(f'# Scale from {int(ast["serves"])} to {int(ast["scale_to"])} servings (factor {factor:.4f})')
        lines.append(f'scale_factor = {factor:.4f}')
        lines.append(f'serves = {ast["scale_to"]}')
        lines.append('for ing in ingredients.values():')
        lines.append('    ing["amount"] = round(ing["amount"] * scale_factor, 4)')
        lines.append('')

    # ── Auto unit upgrade (e.g. 1500g → 1.5kg) ──
    lines.append('UNIT_UPGRADE = {')
    lines.append('    "g":   (1000, "kg",   0.001),')
    lines.append('    "ml":  (1000, "l",    0.001),')
    lines.append('    "tsp": (3,    "tbsp", 1/3),')
    lines.append('}')
    lines.append('for ing in ingredients.values():')
    lines.append('    u = ing["unit"]')
    lines.append('    if u in UNIT_UPGRADE:')
    lines.append('        threshold, bigger, factor = UNIT_UPGRADE[u]')
    lines.append('        if ing["amount"] >= threshold:')
    lines.append('            ing["amount"] = round(ing["amount"] * factor, 4)')
    lines.append('            ing["unit"]   = bigger')
    lines.append('')

    # ── Explicit CONVERT statements ──
    conv_lookup = 'CONV = {"g":1,"kg":1000,"ml":1,"l":1000,"tsp":1,"tbsp":3}'
    for section in ast['sections']:
        for stmt in section['statements']:
            if stmt['type'] == 'CONVERT':
                name    = stmt['ingredient']
                to_unit = stmt['to_unit']
                lines.append(f'# CONVERT {name} TO {to_unit}')
                lines.append(conv_lookup)
                lines.append(f'_ing = ingredients["{name}"]')
                lines.append(f'_base = _ing["amount"] * CONV[_ing["unit"]]')
                lines.append(f'_ing["amount"] = round(_base / CONV["{to_unit}"], 4)')
                lines.append(f'_ing["unit"]   = "{to_unit}"')
                lines.append('')

    # ── Header banner ──
    lines.append('print(f"\\n╔══ {recipe_name} ══")')
    lines.append('print(f"║   Serves  : {int(serves)}")')
    lines.append('')
    lines.append('if allergens:')
    lines.append('    print(f"║   Contains : {", ".join(allergens)}")')
    lines.append('else:')
    lines.append('    print("║   Allergens: none detected")')
    lines.append('')
    lines.append('DIET_BADGE = {')
    lines.append('    "vegan":       "[VEGAN]",')
    lines.append('    "vegetarian":  "[VEGETARIAN]",')
    lines.append('    "gluten-free": "[GLUTEN-FREE]",')
    lines.append('    "dairy-free":  "[DAIRY-FREE]",')
    lines.append('    "nut-free":    "[NUT-FREE]",')
    lines.append('    "halal":       "[HALAL]",')
    lines.append('    "kosher":      "[KOSHER]",')
    lines.append('}')
    lines.append('if diets:')
    lines.append('    badges = " ".join(DIET_BADGE.get(d, f"[{d.upper()}]") for d in diets)')
    lines.append('    print(f"║   Diet     : {badges}")')
    lines.append('print("╚" + "═" * 40)')
    lines.append('')

    # ── Ingredients list ──
    lines.append('print("\\nIngredients:")')
    lines.append('for name, ing in ingredients.items():')
    lines.append('    amt = ing["amount"]')
    lines.append('    display = int(amt) if amt == int(amt) else amt')
    lines.append('    print(f\'  {display}{ing["unit"]}  {name}\')')
    lines.append('')

    # ── Sections ──
    for section in ast['sections']:
        lines.append(f'print("\\n── {section["name"]} ──")')
        step_num = 1
        for stmt in section['statements']:
            if stmt['type'] == 'STEP':
                lines.append(f'print("  {step_num}. {stmt["text"]}")')
                step_num += 1
            elif stmt['type'] == 'BAKE':
                lines.append(
                    f'print("  Bake at {stmt["temp"]}{stmt["temp_unit"]} '
                    f'for {stmt["duration"]}{stmt["time_unit"]}")'
                )
            elif stmt['type'] == 'MIX':
                items = ', '.join(stmt['ingredients'])
                lines.append(f'print("  Mix: {items}")')
            elif stmt['type'] == 'CONVERT':
                pass  # already emitted above

    lines.append('print("")')
    return '\n'.join(lines)

# ═══════════════════════════════════════════════
# DRIVER
# ═══════════════════════════════════════════════

def compile_recipe(source):
    print("\n── Stage 1: Lexing ──")
    tokens = tokenize(source)
    print(f"  [OK] {len(tokens)} tokens produced")

    print("── Stage 2: Parsing ──")
    ast = Parser(tokens).parse()
    print(f"  [OK] AST built — recipe: '{ast['name']}'")

    print("── Stage 3: Semantic Analysis ──")
    ast = analyse(ast)

    print("── Stage 4: Code Generation ──")
    code = generate(ast)
    print("  [OK] Python code generated\n")
    return code

if __name__ == '__main__':
    if len(sys.argv) > 1:
        source = open(sys.argv[1], encoding='utf-8-sig').read()
    else:
        print("Usage: python recipelang.py cake.dsl")
        sys.exit(1)

    output = compile_recipe(source)

    with open('output.py', 'w', encoding='utf-8') as f:
        f.write(output)

    print("── Generated output.py ──")
    exec(output)