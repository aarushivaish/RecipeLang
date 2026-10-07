import re, sys
from dataclasses import dataclass, field
from typing import List, Optional, Union

@dataclass
class IngredientNode:
    name:   str
    amount: float
    unit:   str

    def accept(self, visitor):
        return visitor.visit_ingredient(self)

@dataclass
class StepNode:
    text: str

    def accept(self, visitor):
        return visitor.visit_step(self)

@dataclass
class BakeNode:
    temp:      float
    temp_unit: str
    duration:  float
    time_unit: str

    def accept(self, visitor):
        return visitor.visit_bake(self)


@dataclass
class MixNode:
    ingredients: List[str]

    def accept(self, visitor):
        return visitor.visit_mix(self)

@dataclass
class ConvertNode:
    ingredient: str
    to_unit: str

    def accept(self, visitor):
        return visitor.visit_convert(self)

# A statement inside a section can be any of these
Statement = Union[StepNode, BakeNode, MixNode, ConvertNode]

@dataclass
class SectionNode:
    name:       str
    statements: List[Statement] = field(default_factory=list)

    def accept(self, visitor):
        return visitor.visit_section(self)

@dataclass
class RecipeNode:
    name:        str
    serves:      float
    ingredients: List[IngredientNode]  = field(default_factory=list)
    allergens:   List[str]             = field(default_factory=list)
    diets:       List[str]             = field(default_factory=list)
    sections:    List[SectionNode]     = field(default_factory=list)
    scale_to:    Optional[float]       = None

    def accept(self, visitor):
        return visitor.visit_recipe(self)

# ═══════════════════════════════════════════════
# BASE VISITOR
# ═══════════════════════════════════════════════

class ASTVisitor:
    def visit_recipe(self,      node): raise NotImplementedError
    def visit_section(self,     node): raise NotImplementedError
    def visit_ingredient(self,  node): raise NotImplementedError
    def visit_step(self,        node): raise NotImplementedError
    def visit_bake(self,        node): raise NotImplementedError
    def visit_mix(self,         node): raise NotImplementedError
    def visit_convert(self,     node): raise NotImplementedError
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
        self.consume('KEYWORD', 'RECIPE')
        name   = self.consume('STRING')[1].strip('"')
        self.consume('KEYWORD', 'SERVES')
        serves = float(self.consume('NUMBER')[1])

        ingredients = []
        while self.peek()[1] == 'INGREDIENT':
            ingredients.append(self.parse_ingredient())

        allergens = []
        if self.peek()[1] == 'ALLERGEN':
            self.consume('KEYWORD', 'ALLERGEN')
            self.consume('KEYWORD', 'CONTAINS')
            while self.peek()[0] == 'NAME':
                allergens.append(self.consume('NAME')[1])

        diets = []
        if self.peek()[1] == 'DIET':
            self.consume('KEYWORD', 'DIET')
            self.consume('KEYWORD', 'CLASSIFY')
            while self.peek()[0] == 'NAME':
                diets.append(self.consume('NAME')[1])

        sections = []
        while self.peek()[0] != 'EOF' and self.peek()[1] != 'SCALE':
            if self.peek()[1] in SECTION_KEYWORDS:
                sections.append(self.parse_section())
            else:
                raise SyntaxError(
                    f"Line {self.peek()[2]}: expected a section "
                    f"(PREP/COOK/ASSEMBLE/SERVE), got {self.peek()[1]!r}"
                )

        scale_to = None
        if self.peek()[1] == 'SCALE':
            self.consume('KEYWORD', 'SCALE')
            self.consume('KEYWORD', 'TO')
            scale_to = float(self.consume('NUMBER')[1])

        return RecipeNode(
            name=name,
            serves=serves,
            ingredients=ingredients,
            allergens=allergens,
            diets=diets,
            sections=sections,
            scale_to=scale_to
        )

    def parse_ingredient(self):
        self.consume('KEYWORD', 'INGREDIENT')
        name   = self.consume('NAME')[1]
        amount = float(self.consume('NUMBER')[1])
        unit   = self.consume('UNIT')[1] if self.peek()[0] == 'UNIT' else ''
        return IngredientNode(name=name, amount=amount, unit=unit)

    def parse_section(self):
        section_name = self.consume('KEYWORD')[1]
        statements   = []
        while (self.peek()[0] != 'EOF'
               and self.peek()[1] not in SECTION_KEYWORDS
               and self.peek()[1] != 'SCALE'):
            statements.append(self.parse_statement())
        return SectionNode(name=section_name, statements=statements)

    def parse_statement(self):
        tok = self.peek()

        if tok[1] == 'STEP':
            self.consume('KEYWORD', 'STEP')
            text = self.consume('STRING')[1].strip('"')
            return StepNode(text=text)

        elif tok[1] == 'BAKE':
            self.consume('KEYWORD', 'BAKE')
            temp      = float(self.consume('NUMBER')[1])
            temp_unit = self.consume('UNIT')[1]
            self.consume('KEYWORD', 'FOR')
            duration  = float(self.consume('NUMBER')[1])
            time_unit = self.consume('UNIT')[1]
            return BakeNode(
                temp=temp, temp_unit=temp_unit,
                duration=duration, time_unit=time_unit
            )

        elif tok[1] == 'MIX':
            self.consume('KEYWORD', 'MIX')
            names = []
            while self.peek()[0] == 'NAME':
                names.append(self.consume('NAME')[1])
            return MixNode(ingredients=names)

        elif tok[1] == 'CONVERT':
            self.consume('KEYWORD', 'CONVERT')
            name        = self.consume('NAME')[1]
            self.consume('KEYWORD', 'TO')
            target_unit = self.consume('UNIT')[1]
            return ConvertNode(ingredient=name, to_unit=target_unit)

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
    for ing in ingredients:                          # ing is now IngredientNode
        key = ing.name.lower()                       # ing.name not ing['name']
        if key in INGREDIENT_ALLERGEN_MAP:
            inferred.add(INGREDIENT_ALLERGEN_MAP[key])
    return inferred

class AnalyserVisitor(ASTVisitor):
    def __init__(self, declared, errors):
        self.declared = declared
        self.errors   = errors

    def visit_recipe(self, node):     pass
    def visit_section(self, node):    pass
    def visit_ingredient(self, node): pass

    def visit_step(self, node):
        pass  # nothing to validate

    def visit_bake(self, node):
        if node.temp <= 0:
            self.errors.append("BAKE temperature must be > 0")
        if node.duration <= 0:
            self.errors.append("BAKE duration must be > 0")

    def visit_mix(self, node):
        for name in node.ingredients:
            if name not in self.declared:
                self.errors.append(f"MIX uses undeclared ingredient '{name}'")

    def visit_convert(self, node):
        if node.ingredient not in self.declared:
            self.errors.append(f"CONVERT references undeclared ingredient '{node.ingredient}'")
        else:
            cur = self.declared[node.ingredient].unit
            if not units_compatible(cur, node.to_unit):
                self.errors.append(
                    f"CONVERT: cannot convert '{node.ingredient}' "
                    f"from '{cur}' to '{node.to_unit}'"
                )

def analyse(ast):
    errors   = []
    warnings = []
    declared = {ing.name: ing for ing in ast.ingredients}

    if ast.serves <= 0:
        errors.append("SERVES must be a positive number")

    if not ast.sections:
        errors.append("Recipe must have at least one section")

    declared_allergens = set(ast.allergens)
    inferred_allergens = infer_allergens(ast.ingredients)
    all_allergens      = declared_allergens | inferred_allergens

    for allergen in declared_allergens:
        if allergen not in KNOWN_ALLERGENS:
            errors.append(f"Unknown allergen '{allergen}'")

    for missing in sorted(inferred_allergens - declared_allergens):
        warnings.append(f"Ingredient implies allergen '{missing}' — consider declaring it")

    for diet in ast.diets:
        if diet not in KNOWN_DIETS:
            errors.append(f"Unknown diet '{diet}'")
        elif diet in DIET_CONFLICTS:
            conflicts = DIET_CONFLICTS[diet] & all_allergens
            if conflicts:
                errors.append(f"DIET '{diet}' conflicts with: {', '.join(sorted(conflicts))}")

    for section in ast.sections:
        for stmt in section.statements:
            stmt.accept(AnalyserVisitor(declared, errors))

    if ast.scale_to is not None and ast.scale_to <= 0:
        errors.append("SCALE TO value must be positive")

    for w in warnings:
        print(f"  [WARN]  {w}")
    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        sys.exit(1)

    print(f"  [OK] {len(declared)} ingredients, {len(ast.sections)} sections")
    print(f"  [OK] Allergens : {', '.join(sorted(all_allergens)) or 'none detected'}")
    print(f"  [OK] Diet tags : {', '.join(ast.diets) or 'none declared'}")
    return ast

# ═══════════════════════════════════════════════
# STAGE 4: CODE GENERATOR
# ═══════════════════════════════════════════════

class CodeGenVisitor(ASTVisitor):
    def __init__(self, ast, all_allergens):
        self.ast          = ast
        self.all_allergens = all_allergens
        self.lines        = []
        self.step_num     = 1

    def visit_recipe(self, node):
        self.lines.append('# Generated by RecipeLang compiler')
        self.lines.append('')
        self.lines.append('ingredients = {')
        for ing in node.ingredients:
            ing.accept(self)
        self.lines.append('}')
        self.lines.append('')
        self.lines.append(f'recipe_name = "{node.name}"')
        self.lines.append(f'serves      = {node.serves}')
        self.lines.append(f'allergens   = {self.all_allergens}')
        self.lines.append(f'diets       = {node.diets}')
        self.lines.append('')

        if node.scale_to:
            factor = node.scale_to / node.serves
            self.lines.append(f'scale_factor = {factor:.4f}')
            self.lines.append(f'serves = {node.scale_to}')
            self.lines.append('for ing in ingredients.values():')
            self.lines.append('    ing["amount"] = round(ing["amount"] * scale_factor, 4)')
            self.lines.append('')

        self.lines.append('UNIT_UPGRADE = {')
        self.lines.append('    "g":   (1000, "kg",   0.001),')
        self.lines.append('    "ml":  (1000, "l",    0.001),')
        self.lines.append('    "tsp": (3,    "tbsp", 1/3),')
        self.lines.append('}')
        self.lines.append('for ing in ingredients.values():')
        self.lines.append('    u = ing["unit"]')
        self.lines.append('    if u in UNIT_UPGRADE:')
        self.lines.append('        threshold, bigger, factor = UNIT_UPGRADE[u]')
        self.lines.append('        if ing["amount"] >= threshold:')
        self.lines.append('            ing["amount"] = round(ing["amount"] * factor, 4)')
        self.lines.append('            ing["unit"]   = bigger')
        self.lines.append('')

        self.lines.append('print(f"\\n╔══ {recipe_name} ══")')
        self.lines.append('print(f"║   Serves  : {int(serves)}")')
        self.lines.append('if allergens:')
        self.lines.append('    print(f"║   Contains : {", ".join(allergens)}")')
        self.lines.append('else:')
        self.lines.append('    print("║   Allergens: none detected")')
        self.lines.append('DIET_BADGE = {')
        self.lines.append('    "vegan":       "[VEGAN]",')
        self.lines.append('    "vegetarian":  "[VEGETARIAN]",')
        self.lines.append('    "gluten-free": "[GLUTEN-FREE]",')
        self.lines.append('    "dairy-free":  "[DAIRY-FREE]",')
        self.lines.append('    "nut-free":    "[NUT-FREE]",')
        self.lines.append('    "halal":       "[HALAL]",')
        self.lines.append('    "kosher":      "[KOSHER]",')
        self.lines.append('}')
        self.lines.append('if diets:')
        self.lines.append('    badges = " ".join(DIET_BADGE.get(d, f"[{d.upper()}]") for d in diets)')
        self.lines.append('    print(f"║   Diet     : {badges}")')
        self.lines.append('print("╚" + "═" * 40)')
        self.lines.append('')
        self.lines.append('print("\\nIngredients:")')
        self.lines.append('for name, ing in ingredients.items():')
        self.lines.append('    amt = ing["amount"]')
        self.lines.append('    display = int(amt) if amt == int(amt) else amt')
        self.lines.append('    print(f\'  {display}{ing["unit"]}  {name}\')')
        self.lines.append('')

        for section in node.sections:
            self.step_num = 1
            section.accept(self)

    def visit_ingredient(self, node):
        self.lines.append(
            f'    "{node.name}": '
            f'{{"amount": {node.amount}, "unit": "{node.unit}"}},')

    def visit_section(self, node):
        self.lines.append(f'print("\\n── {node.name} ──")')
        for stmt in node.statements:
            stmt.accept(self)

    def visit_step(self, node):
        self.lines.append(f'print("  {self.step_num}. {node.text}")')
        self.step_num += 1

    def visit_bake(self, node):
        self.lines.append(
            f'print("  Bake at {node.temp}{node.temp_unit} '
            f'for {node.duration}{node.time_unit}")')

    def visit_mix(self, node):
        items = ', '.join(node.ingredients)
        self.lines.append(f'print("  Mix: {items}")')

    def visit_convert(self, node):
        self.lines.append(f'CONV = {{"g":1,"kg":1000,"ml":1,"l":1000,"tsp":1,"tbsp":3}}')
        self.lines.append(f'_ing = ingredients["{node.ingredient}"]')
        self.lines.append(f'_base = _ing["amount"] * CONV[_ing["unit"]]')
        self.lines.append(f'_ing["amount"] = round(_base / CONV["{node.to_unit}"], 4)')
        self.lines.append(f'_ing["unit"]   = "{node.to_unit}"')
        self.lines.append('')

def generate(ast):
    inferred      = infer_allergens(ast.ingredients)
    all_allergens = sorted(set(ast.allergens) | inferred)

    visitor = CodeGenVisitor(ast, all_allergens)
    ast.accept(visitor)
    return '\n'.join(visitor.lines)

# ═══════════════════════════════════════════════
# DRIVER
# ═══════════════════════════════════════════════

def compile_recipe(source):
    print("\n── Stage 1: Lexing ──")
    tokens = tokenize(source)
    print(f"  [OK] {len(tokens)} tokens produced")

    print("── Stage 2: Parsing ──")
    ast = Parser(tokens).parse()
    print(f"  [OK] AST built — recipe: '{ast.name}'")

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