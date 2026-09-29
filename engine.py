"""Bounded AST mathematics. Never execute user expressions or send them to a model."""
import ast
import math
import re
from fractions import Fraction


class MathError(ValueError):
    pass


WORDS = {
    'en': {'add': 'plus', 'sub': 'minus', 'mul': 'times', 'frac': 'fraction, numerator', 'den': 'denominator', 'end': 'end fraction', 'pow': 'to the power', 'group': 'open group', 'close': 'close group', 'root': 'square root of', 'eq': 'equals', 'row': 'row', 'matrix': 'matrix', 'read': 'Read the structure', 'calc': 'Calculate using the order of operations', 'answer': 'Result', 'collect': 'Move all terms to the left and combine like terms', 'linear': 'Isolate x by dividing by its coefficient', 'quad': 'Use the quadratic formula', 'none': 'There is no real solution.', 'all': 'Every real value of x satisfies this equation.', 'det': 'Calculate the determinant', 'transpose': 'Swap rows and columns', 'neg': 'negative', 'abs': 'absolute value of', 'log': 'log base 10 of', 'ln': 'natural log of', 'sin': 'sine of', 'cos': 'cosine of', 'tan': 'tangent of', 'deg': 'degrees'},
    'hi': {'add': 'जोड़', 'sub': 'घटा', 'mul': 'गुणा', 'frac': 'भिन्न शुरू, अंश', 'den': 'हर', 'end': 'भिन्न समाप्त', 'pow': 'की घात', 'group': 'कोष्ठक शुरू', 'close': 'कोष्ठक समाप्त', 'root': 'का वर्गमूल', 'eq': 'बराबर', 'row': 'पंक्ति', 'matrix': 'आव्यूह', 'read': 'गणित की संरचना पढ़ें', 'calc': 'संक्रियाओं के क्रम के अनुसार गणना करें', 'answer': 'परिणाम', 'collect': 'सभी पद बाईं ओर लाएँ और समान पद जोड़ें', 'linear': 'गुणांक से भाग देकर x का मान निकालें', 'quad': 'द्विघात सूत्र का उपयोग करें', 'none': 'कोई वास्तविक हल नहीं है।', 'all': 'x का प्रत्येक वास्तविक मान इस समीकरण को संतुष्ट करता है।', 'det': 'सारणिक की गणना करें', 'transpose': 'पंक्तियों और स्तंभों की अदला-बदली करें', 'neg': 'ऋण', 'abs': 'का निरपेक्ष मान', 'log': 'का लॉग आधार 10', 'ln': 'का प्राकृतिक लॉग', 'sin': 'का ज्या (sine)', 'cos': 'का कोज्या (cosine)', 'tan': 'का स्पर्शज्या (tangent)', 'deg': 'डिग्री'},
    'ta': {'add': 'கூட்டல்', 'sub': 'கழித்தல்', 'mul': 'பெருக்கல்', 'frac': 'பின்னம் தொடக்கம், தொகுதி', 'den': 'பகுதி', 'end': 'பின்னம் முடிவு', 'pow': 'அடுக்கு', 'group': 'அடைப்புக்குறி தொடக்கம்', 'close': 'அடைப்புக்குறி முடிவு', 'root': 'வர்க்கமூலம்', 'eq': 'சமம்', 'row': 'வரிசை', 'matrix': 'அணி', 'read': 'கணித அமைப்பைப் படிக்கவும்', 'calc': 'செயல்பாடுகளின் வரிசைப்படி கணக்கிடவும்', 'answer': 'விடை', 'collect': 'அனைத்து உறுப்புகளையும் இடப்பக்கம் கொண்டு வந்து ஒத்த உறுப்புகளைச் சேர்க்கவும்', 'linear': 'கெழுவால் வகுத்து x இன் மதிப்பைக் காணவும்', 'quad': 'இருபடிச் சமன்பாட்டு வாய்ப்பாட்டைப் பயன்படுத்தவும்', 'none': 'மெய்யெண் தீர்வு இல்லை.', 'all': 'x இன் அனைத்து மெய்யெண் மதிப்புகளும் இந்தச் சமன்பாட்டை நிறைவு செய்கின்றன.', 'det': 'அணிக்கோவையைக் கணக்கிடவும்', 'transpose': 'வரிசைகளையும் நிரல்களையும் மாற்றவும்', 'neg': 'எதிர்மறை', 'abs': 'இன் முழுமதிப்பு', 'log': 'இன் மட 10 மடக்கை', 'ln': 'இன் இயல் மடக்கை', 'sin': 'இன் சைன்', 'cos': 'இன் கொசைன்', 'tan': 'இன் டேன்ஜென்ட்', 'deg': 'டிகிரி'},
}

# Function names accepted in ast.Call nodes -- kept as an explicit allowlist so
# `number()`/`speak()` never evaluate an arbitrary attribute or builtin.
UNARY_FUNCTIONS = {'sqrt', 'abs', 'log', 'ln', 'sin', 'cos', 'tan'}


def fmt(value):
    if isinstance(value, Fraction):
        return str(value.numerator) if value.denominator == 1 else f'{value.numerator}/{value.denominator}'
    return f'{value:.8g}'


def normalize(text):
    if not text.strip() or len(text) > 500:
        raise MathError('Enter a question between 1 and 500 characters.')
    text = text.strip().lower().translate(str.maketrans('०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯', '01234567890123456789'))
    for a, b in [('×', '*'), ('÷', '/'), ('−', '-'), ('²', '^2'), ('³', '^3'), ('√', 'sqrt'), ('\\times', '*'), ('\\div', '/')]:
        text = text.replace(a, b)
    replacements = {'to the power of': '^', 'raised to': '^', 'squared': '^2', 'cubed': '^3', 'multiplied by': '*', 'divided by': '/', 'square root of': 'sqrt', 'plus': '+', 'minus': '-', 'times': '*', 'over': '/', 'equals': '=', 'equal to': '=', 'जोड़': '+', 'प्लस': '+', 'घटा': '-', 'माइनस': '-', 'गुणा': '*', 'भाग': '/', 'बराबर': '=', 'கூட்டல்': '+', 'கழித்தல்': '-', 'பெருக்கல்': '*', 'வகுத்தல்': '/', 'சமம்': '='}
    for source, target in replacements.items():
        text = re.sub(r'(?<!\w)' + re.escape(source) + r'(?!\w)', target, text)
    for n, word in enumerate(['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']):
        text = re.sub(r'\b' + word + r'\b', str(n), text)
    text = re.sub(r'^(please\s+)?(solve|calculate|evaluate|simplify)(\s+for\s+x)?\s*:?\s*', '', text)
    text = text.rstrip('?. ')
    text = re.sub(r'sqrt\s*(\d+(?:\.\d+)?)', r'sqrt(\1)', text)
    text = re.sub(r'(\d|\))\s*(?=x\b|\()', r'\1*', text)
    text = re.sub(r'\bx\s*(?=\()', 'x*', text)
    return text.replace('^', '**')


def parse(text):
    try:
        node = ast.parse(text.strip(), mode='eval').body
    except (SyntaxError, RecursionError):
        raise MathError('Check the expression. Use parentheses for fractions, for example (1+2)/(3+4).')
    if len(list(ast.walk(node))) > 120:
        raise MathError('Please split this into a shorter expression.')
    return node


def bounded(value):
    if abs(value) > 10**30 or (isinstance(value, Fraction) and value.denominator > 10**30):
        raise MathError('The numbers are too large. Please use smaller values.')
    return value


def number(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if not math.isfinite(node.value):
            raise MathError('Use finite numbers.')
        return bounded(Fraction(str(node.value)))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return (-1 if isinstance(node.op, ast.USub) else 1) * number(node.operand)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in UNARY_FUNCTIONS and len(node.args) == 1 and not node.keywords:
        name = node.func.id
        value = number(node.args[0])
        if name == 'sqrt':
            if value < 0:
                raise MathError('Square roots of negative numbers are not supported in real-number mode.')
            if isinstance(value, Fraction):
                a, b = math.isqrt(value.numerator), math.isqrt(value.denominator)
                if a*a == value.numerator and b*b == value.denominator:
                    return Fraction(a, b)
            return math.sqrt(value)
        if name == 'abs':
            return bounded(abs(value))
        if name == 'log':
            if value <= 0: raise MathError('log() needs a positive number.')
            return math.log10(value)
        if name == 'ln':
            if value <= 0: raise MathError('ln() needs a positive number.')
            return math.log(value)
        if name in ('sin', 'cos', 'tan'):
            radians = math.radians(float(value))
            if name == 'tan' and abs(math.cos(radians)) < 1e-12:
                raise MathError('tan() is undefined at this angle.')
            return getattr(math, name)(radians)
    if isinstance(node, ast.BinOp):
        a, b = number(node.left), number(node.right)
        if isinstance(node.op, ast.Add): return bounded(a+b)
        if isinstance(node.op, ast.Sub): return bounded(a-b)
        if isinstance(node.op, ast.Mult): return bounded(a*b)
        if isinstance(node.op, ast.Div):
            if b == 0: raise MathError('Division by zero is undefined. Check the denominator.')
            return bounded(a/b)
        if isinstance(node.op, ast.Pow):
            if b != int(b) or abs(b) > 12:
                raise MathError('Use whole-number powers from −12 to 12. Use sqrt() for square roots.')
            if a == 0 and b <= 0: raise MathError('Zero cannot be raised to a zero or negative power here.')
            return bounded(a ** int(b))
    raise MathError('Use numbers, +, −, *, /, powers, sqrt()/abs()/log()/ln()/sin()/cos()/tan(), or an equation in x. General word problems are not supported yet.')


def poly(node):
    if isinstance(node, ast.Name) and node.id == 'x': return [Fraction(0), Fraction(1), Fraction(0)]
    if not any(isinstance(n, ast.Name) and n.id == 'x' for n in ast.walk(node)):
        value = number(node)
        if not isinstance(value, Fraction): raise MathError('Equation coefficients must be rational numbers.')
        return [value, Fraction(0), Fraction(0)]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return [v * (-1 if isinstance(node.op, ast.USub) else 1) for v in poly(node.operand)]
    if isinstance(node, ast.BinOp):
        a, b = poly(node.left), poly(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            sign = -1 if isinstance(node.op, ast.Sub) else 1
            return [bounded(x+sign*y) for x, y in zip(a, b)]
        if isinstance(node.op, ast.Mult):
            result = [Fraction(0)] * 5
            for i in range(3):
                for j in range(3): result[i+j] += bounded(a[i]*b[j])
            if any(result[3:]): raise MathError('Only linear and quadratic equations are supported.')
            return [bounded(v) for v in result[:3]]
        if isinstance(node.op, ast.Div):
            if b[1] or b[2] or b[0] == 0: raise MathError('Equation denominators must be nonzero constants.')
            return [bounded(v/b[0]) for v in a]
        if isinstance(node.op, ast.Pow) and not b[1] and not b[2] and b[0] in (0, 1, 2):
            if b[0] == 0: raise MathError('Rewrite variable powers of zero explicitly as 1, checking the domain first.')
            if b[0] == 1: return a
            return poly(ast.BinOp(left=node.left, op=ast.Mult(), right=node.left))
    raise MathError('Use a linear or quadratic equation in x, such as 2*x + 3 = 11.')


def speak(node, lang='en'):
    w = WORDS[lang]
    if isinstance(node, ast.Constant): return str(node.value)
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.UnaryOp): return f"{w['neg'] if isinstance(node.op, ast.USub) else w['add']} {speak(node.operand, lang)}"
    if isinstance(node, ast.Call):
        word = w.get(node.func.id, w['root']) if node.func.id != 'sqrt' else w['root']
        suffix = f", {w['deg']}" if node.func.id in ('sin', 'cos', 'tan') else ''
        return f"{word}, {speak(node.args[0], lang)}{suffix}, {w['close']}"
    if isinstance(node, ast.BinOp):
        a, b = speak(node.left, lang), speak(node.right, lang)
        if isinstance(node.op, ast.Div): return f"{w['frac']}, {a}; {w['den']}, {b}; {w['end']}"
        op = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Pow: 'pow'}[type(node.op)]
        return f"{w['group']}, {a}, {w[op]}, {b}, {w['close']}"
    return ''


BRAILLE = dict(zip('abcdefghijklmnopqrstuvwxyz', '⠁⠃⠉⠙⠑⠋⠛⠓⠊⠚⠅⠇⠍⠝⠕⠏⠟⠗⠎⠏⠟⠗⠎⠞⠥⠧'))
# Uncontracted English literary alphabet only; not a mathematical Braille code.
BRAILLE = dict(zip('abcdefghijklmnopqrstuvwxyz', '⠁⠃⠉⠙⠑⠋⠛⠓⠊⠚⠅⠇⠍⠝⠕⠏⠟⠗⠎⠞⠥⠧⠺⠭⠽⠵'))


def braille(text):
    output, unsupported, in_number = [], set(), False
    for char in text:
        if char.isascii() and char.isdigit():
            if not in_number: output.append('⠼')
            output.append(BRAILLE['jabcdefghi'[int(char)]])
            in_number = True
        elif char.lower() in BRAILLE:
            if in_number and char.lower() in 'abcdefghij': output.append('⠰')
            if char.isupper(): output.append('⠠')
            output.append(BRAILLE[char.lower()])
            in_number = False
        elif char in ' \n':
            output.append(char)
            in_number = False
        else:
            output.append(char)
            unsupported.add(char)
            in_number = False
    return {'text': ''.join(output), 'unsupported': sorted(unsupported), 'notice': 'English letters and digits preview only. Operators remain in print. This is not Nemeth, UEB mathematics, or Bharati Braille. A screen cannot produce tactile dots.'}


def determinant(rows):
    if len(rows) == 1: return rows[0][0]
    return sum(((-1)**i) * rows[0][i] * determinant([r[:i] + r[i+1:] for r in rows[1:]]) for i in range(len(rows)))


def solve(question, language='en'):
    lang = language if isinstance(language, str) and language in WORDS else 'en'
    w = WORDS[lang]
    expression = normalize(question)
    steps = []
    operation = re.match(r'^(det|determinant|transpose)\s*', expression)
    if expression.startswith('[') or operation:
        node = parse(expression[operation.end():] if operation else expression)
        if not isinstance(node, ast.List) or not 1 <= len(node.elts) <= 3:
            raise MathError('Use a matrix up to 3 by 3, for example [[1,2],[3,4]].')
        rows = []
        for row in node.elts:
            if not isinstance(row, ast.List) or not 1 <= len(row.elts) <= 3: raise MathError('Each matrix row must contain 1 to 3 numbers.')
            rows.append([number(cell) for cell in row.elts])
        if len({len(r) for r in rows}) != 1: raise MathError('All matrix rows must have the same number of entries.')
        structure = f"{w['matrix']}, {len(rows)} × {len(rows[0])}. " + '; '.join(f"{w['row']} {i+1}: " + ', '.join(fmt(x) for x in row) for i, row in enumerate(rows))
        if operation and operation[1] in ('det', 'determinant'):
            if len(rows) != len(rows[0]): raise MathError('A determinant needs a square matrix.')
            answer = fmt(bounded(determinant(rows)))
            formula = f'({fmt(rows[0][0])} × {fmt(rows[1][1])}) − ({fmt(rows[0][1])} × {fmt(rows[1][0])})' if len(rows) == 2 else ' + '.join(f'({fmt(rows[0][i])}) × ({fmt(((-1)**i)*determinant([r[:i]+r[i+1:] for r in rows[1:]]))})' for i in range(len(rows))) if len(rows)>1 else fmt(rows[0][0])
            steps.append({'title': w['det'], 'text': formula, 'speech': formula})
        else:
            if operation:
                rows = list(zip(*rows))
                steps.append({'title': w['transpose'], 'text': 'Aᵀ', 'speech': w['transpose']})
            answer = '[' + ', '.join('[' + ', '.join(fmt(v) for v in r) + ']' for r in rows) + ']'
        kind = 'Matrix'
        answer_speech = answer if operation and operation[1] in ('det','determinant') else '; '.join(f"{w['row']} {i+1}: " + ', '.join(fmt(v) for v in row) for i,row in enumerate(rows))
    elif '=' in expression:
        if expression.count('=') != 1: raise MathError('Enter one equation at a time.')
        left, right = [parse(s) for s in expression.split('=')]
        c, b, a = [bounded(x-y) for x,y in zip(poly(left), poly(right))]
        structure = f"{speak(left, lang)}; {w['eq']}; {speak(right, lang)}"
        standard = f'({fmt(a)})*x^2 + ({fmt(b)})*x + ({fmt(c)}) = 0'
        steps.append({'title': w['collect'], 'text': standard, 'speech': speak(parse(standard.split('=')[0].replace('^','**')), lang) + ' ' + w['eq'] + ' 0'})
        if a == 0:
            if b == 0: answer = w['all'] if c == 0 else w['none']
            else:
                answer = 'x = ' + fmt(-c/b)
                calculation = f'({fmt(-c)}) / ({fmt(b)})'
                steps.append({'title': w['linear'], 'text': calculation, 'speech': speak(parse(calculation), lang)})
        else:
            d = b*b - 4*a*c
            steps.append({'title': w['quad'], 'text': f'x = (−b ± √(b² − 4ac)) / (2a); D = {fmt(d)}', 'speech': f"{w['frac']}, {w['neg']} b, ± {w['root']} D; {w['den']}, 2 {w['mul']} a; {w['end']}. D {w['eq']} {fmt(d)}"})
            if d < 0: answer = w['none']
            else:
                root = number(parse(f'sqrt({fmt(d)})'))
                answers = sorted(set([(-b-root)/(2*a), (-b+root)/(2*a)]))
                answer = 'x ' + ('≈ ' if isinstance(root, float) else '= ') + ', '.join(fmt(v) for v in answers)
        kind = 'Equation'
        answer_speech = answer.replace('=', w['eq'])
    else:
        node = parse(expression)
        result = number(node)
        structure = speak(node, lang)
        answer = ('≈ ' if isinstance(result, float) else '') + fmt(result)
        # Postorder explanations preserve the expression tree and operation order.
        for child in ast.walk(node):
            if isinstance(child, (ast.BinOp, ast.Call)):
                value = number(child)
                steps.append({'title': w['calc'], 'text': ast.unparse(child).replace('**', '^') + ' = ' + fmt(value), 'speech': speak(child, lang) + ', ' + w['eq'] + ', ' + speak(parse(fmt(value)), lang)})
        steps.reverse()
        kind = 'Arithmetic'
        answer_speech = speak(parse(fmt(result)), lang)
    steps = [{'title': w['read'], 'text': structure, 'speech': structure}] + steps
    steps.append({'title': w['answer'], 'text': answer, 'speech': answer_speech})
    return {'question': question.strip(), 'normalized': expression.replace('**', '^'), 'language': lang, 'kind': kind, 'answer': answer, 'structure': structure, 'steps': steps, 'braille': braille(answer), 'engine': 'Local calculation • no AI-generated answers'}
