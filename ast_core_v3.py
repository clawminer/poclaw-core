import random
import string
import math
import datetime
import re
import hashlib
import binascii
import zlib
import base64
import urllib.parse
import html
import codecs
from functools import reduce
import numpy as np
import scipy.special
import scipy.stats

# ==========================================
# 1. 基础工具与辅助函数 (Standard Utils)
# ==========================================

def is_prime(n):
    if n < 2: return 0
    for i in range(2, int(math.isqrt(n)) + 1):
        if n % i == 0: return 0
    return 1

def fib(n):
    if n <= 0: return 0
    elif n == 1: return 1
    a, b = 0, 1
    for _ in range(2, min(n, 100) + 1):
        a, b = b, a + b
    return b

def shift_chars(s, n):
    """Standard Caesar Cipher with wrapping"""
    res = ""
    for c in s:
        if c.isalpha():
            base = ord('A') if c.isupper() else ord('a')
            res += chr((ord(c) - base + n) % 26 + base)
        else: res += c
    return res

def random_val(t):
    if t == 'STR': return "".join(random.choices(string.ascii_lowercase, k=random.randint(3, 6)))
    if t == 'INT': return random.randint(2, 10)
    if t == 'LIST': return [random.randint(1, 9) for _ in range(random.randint(3, 5))]
    if t == 'POINT': return (random.randint(0, 10), random.randint(0, 10))
    return None

def safe_eval_list(l): return l if isinstance(l, list) else []
def safe_int(n): 
    try: return int(n)
    except: return 0

def get_date(d): return datetime.date(d[0], d[1], d[2])
def date_tuple(dt): return (dt.year, dt.month, dt.day)

# ==========================================
# 2. 120 标准原子操作注册表 (Standard Ops)
# ==========================================

OPS = {}
def reg(name, out_type, arg_types, func, tmpl):
    OPS[name] = {'out': out_type, 'args': arg_types, 'func': func, 'tmpl': tmpl}

# --- 1. String Manipulation (Standard Python) ---
reg('StringReverse', 'STR', ['STR'], lambda s: s[::-1], ["reverse string {}", "flip text {}", "invert order of {}", "mirror string {}", "backwards version of {}"])
reg('StringUpper', 'STR', ['STR'], lambda s: s.upper(), ["convert {} to uppercase", "make {} caps", "all caps of {}", "uppercase transform {}", "capitalize all chars in {}"])
reg('StringLower', 'STR', ['STR'], lambda s: s.lower(), ["convert {} to lowercase", "make {} small", "lowercase of {}", "downcase {}", "all lower in {}"])
reg('SliceHead', 'STR', ['STR', 'INT'], lambda s, n: s[:max(1, n)], ["get first {} characters of {}", "slice head {} of {}", "take {} chars from start of {}", "prefix {} from {}", "leading {} symbols of {}"])
reg('SliceTail', 'STR', ['STR', 'INT'], lambda s, n: s[-max(1, n):], ["get last {} characters of {}", "slice tail {} of {}", "take {} chars from end of {}", "suffix {} from {}", "trailing {} symbols of {}"])
reg('Concatenate', 'STR', ['STR', 'STR'], lambda a, b: a + b, ["concatenate {} and {}", "join string {} with {}", "append {} to {}", "merge strings {} and {}", "chain {} after {}"])
reg('RemoveChar', 'STR', ['STR', 'STR'], lambda s, c: s.replace(c[0] if c else 'a', ''), ["remove character {} from {}", "delete char {} in {}", "strip {} out of {}", "eliminate {} from string {}", "erase {} in {}"])
reg('RepeatString', 'STR', ['STR', 'INT'], lambda s, n: s * max(1, min(n, 5)), ["repeat string {} {} times", "duplicate {} {} times", "echo {} repeated {} times", "replicate {} by factor {}", "{} copied {} times"])
reg('SwapCase', 'STR', ['STR'], lambda s: s.swapcase(), ["swap case of {}", "toggle case for {}", "invert letter case of {}", "flip upper/lower in {}", "alternate case of {}"])
reg('CaesarCipher', 'STR', ['STR', 'INT'], lambda s, n: shift_chars(s, n), ["apply caesar cipher to {} with shift {}", "shift chars in {} by {}", "rotate alphabet of {} by {} positions", "caesar encode {} offset {}", "letter shift {} step {}"])
reg('StripWhitespace', 'STR', ['STR'], lambda s: s.strip(), ["strip whitespace from {}", "trim {}", "remove leading and trailing spaces of {}", "clean edges of {}", "trim blanks from {}"])
reg('CenterPad', 'STR', ['STR', 'INT'], lambda s, n: s.center(min(n, 20), '*'), ["center {} with padding size {}", "pad center {} to {}", "center-align {} in field of {}", "symmetric pad {} to width {}", "center justify {} at length {}"])
reg('LeftJustify', 'STR', ['STR', 'INT'], lambda s, n: s.ljust(min(n, 20), '*'), ["left justify {} width {}", "pad right of {} to {}", "left-align {} in field {}", "ljust {} to size {}", "anchor {} left with width {}"])
reg('RightJustify', 'STR', ['STR', 'INT'], lambda s, n: s.rjust(min(n, 20), '*'), ["right justify {} width {}", "pad left of {} to {}", "right-align {} in field {}", "rjust {} to size {}", "anchor {} right with width {}"])
reg('ZeroFill', 'STR', ['STR', 'INT'], lambda s, n: s.zfill(min(n, 10)), ["zero fill {} to width {}", "pad zeros to {} size {}", "zero-pad {} to {} digits", "prepend zeros to {} until length {}", "zfill {} with {}"])

# --- 2. Mathematical Functions (Math Lib) ---
reg('Add', 'INT', ['INT', 'INT'], lambda a, b: a + b, ["add {} and {}", "sum of {} and {}", "plus {} with {}", "{} + {}", "total of {} and {}"])
reg('Subtract', 'INT', ['INT', 'INT'], lambda a, b: a - b, ["subtract {} from {}", "difference between {} and {}", "{} minus {}", "take {} away from {}", "deduct {} from {}"])
reg('Multiply', 'INT', ['INT', 'INT'], lambda a, b: a * b, ["multiply {} by {}", "product of {} and {}", "{} times {}", "scale {} by {}", "{} * {}"])
reg('FloorDiv', 'INT', ['INT', 'INT'], lambda a, b: a // b if b!=0 else 0, ["floor divide {} by {}", "integer division {} / {}", "quotient of {} over {}", "whole number {} divided by {}", "truncated division of {} by {}"])
reg('Modulo', 'INT', ['INT', 'INT'], lambda a, b: a % b if b!=0 else 0, ["{} modulo {}", "remainder of {} divided by {}", "{} mod {}", "residue of {} by {}", "{} percent {}"])
reg('Power', 'INT', ['INT', 'INT'], lambda a, b: a ** max(0, min(b, 4)), ["{} to the power of {}", "{} raised to {}", "exponentiate {} by {}", "pow({}, {})", "{} ** {}"])
reg('Absolute', 'INT', ['INT'], lambda a: abs(a), ["absolute value of {}", "magnitude of {}", "abs({})", "distance from zero of {}", "non-negative version of {}"])
reg('Maximum', 'INT', ['INT', 'INT'], lambda a, b: max(a, b), ["maximum of {} and {}", "larger of {} and {}", "max({}, {})", "greater value among {} and {}", "upper bound of {} and {}"])
reg('Minimum', 'INT', ['INT', 'INT'], lambda a, b: min(a, b), ["minimum of {} and {}", "smaller of {} and {}", "min({}, {})", "lesser value among {} and {}", "lower bound of {} and {}"])
reg('IsPrime', 'INT', ['INT'], lambda n: is_prime(n), ["check if {} is prime", "is_prime({})", "primality test on {}", "is {} a prime number", "prime flag of {}"])
reg('Factorial', 'INT', ['INT'], lambda n: math.factorial(max(0, min(n, 10))), ["factorial of {}", "{}!", "{}  factorial", "math.factorial({})", "permutation count {}!"])
reg('GCD', 'INT', ['INT', 'INT'], lambda a, b: math.gcd(a, b), ["greatest common divisor of {} and {}", "gcd({}, {})", "highest common factor of {} and {}", "math.gcd({}, {})", "largest divisor shared by {} and {}"])
reg('LCM', 'INT', ['INT', 'INT'], lambda a, b: math.lcm(a, b), ["least common multiple of {} and {}", "lcm({}, {})", "smallest shared multiple of {} and {}", "math.lcm({}, {})", "LCM of {} and {}"])
reg('IntegerSqrt', 'INT', ['INT'], lambda n: int(math.isqrt(max(0, n))), ["integer square root of {}", "isqrt({})", "floor sqrt of {}", "whole-number sqrt of {}", "int(sqrt({}))"])
reg('SignFunction', 'INT', ['INT'], lambda n: 1 if n>0 else -1 if n<0 else 0, ["sign of {}", "signum({})", "polarity of {}", "positive-negative indicator of {}", "math.copysign direction {}"])

# --- 3. List Processing ---
reg('SumList', 'INT', ['LIST'], lambda l: sum(safe_eval_list(l)), ["sum of elements in {}", "total sum of {}", "add all values in {}", "sum({})", "aggregate {}"])
reg('ProductList', 'INT', ['LIST'], lambda l: math.prod(safe_eval_list(l)) if l else 0, ["product of elements in {}", "multiply all in {}", "math.prod({})", "fold multiply {}", "running product of {}"])
reg('MaxOfList', 'INT', ['LIST'], lambda l: max(safe_eval_list(l)) if l else 0, ["maximum value in {}", "largest in {}", "max({})", "peak element of {}", "highest number in {}"])
reg('MinOfList', 'INT', ['LIST'], lambda l: min(safe_eval_list(l)) if l else 0, ["minimum value in {}", "smallest in {}", "min({})", "lowest element of {}", "floor element of {}"])
reg('ListLength', 'INT', ['LIST'], lambda l: len(safe_eval_list(l)), ["length of list {}", "count items in {}", "len({})", "number of elements in {}", "size of list {}"])
reg('SortList', 'LIST', ['LIST'], lambda l: sorted(safe_eval_list(l)), ["sort list {}", "order elements in {}", "sorted({})", "ascending sort of {}", "arrange {} from low to high"])
reg('ReverseList', 'LIST', ['LIST'], lambda l: safe_eval_list(l)[::-1], ["reverse list {}", "flip order of {}", "invert sequence {}", "backwards list {}", "mirror array {}"])
reg('GetAtIndex', 'INT', ['LIST', 'INT'], lambda l, n: l[n % len(l)] if l else 0, ["get element at index {} from {}", "{}th item of {}", "item at position {} in {}", "{}[{}]", "pick index {} of {}"])
reg('FilterOdds', 'LIST', ['LIST'], lambda l: [x for x in safe_eval_list(l) if x%2!=0], ["filter odd numbers from {}", "keep odds in {}", "extract odd elements of {}", "odd-only subset of {}", "retain odd values in {}"])
reg('FilterEvens', 'LIST', ['LIST'], lambda l: [x for x in safe_eval_list(l) if x%2==0], ["filter even numbers from {}", "keep evens in {}", "extract even elements of {}", "even-only subset of {}", "retain even values in {}"])
reg('UniqueElements', 'LIST', ['LIST'], lambda l: sorted(set(safe_eval_list(l))), ["unique elements of {}", "remove duplicates from {}", "deduplicate {}", "set of {}", "distinct values in {}"])
reg('RotateLeft', 'LIST', ['LIST', 'INT'], lambda l, n: l[n%len(l):] + l[:n%len(l)] if l else [], ["rotate list {} left by {}", "shift {} left {} steps", "cyclic shift {} by {} positions", "deque-rotate {} left {}", "left-roll {} by {}"])
reg('RepeatList', 'LIST', ['LIST', 'INT'], lambda l, n: l * max(1, min(n, 3)), ["repeat list {} {} times", "duplicate list {} {} times", "tile list {} {} times", "replicate array {} {} times", "{} extended {} times"])
reg('PairwiseSum', 'LIST', ['LIST'], lambda l: [x+y for x,y in zip(l, l[1:])], ["pairwise sum of {}", "add adjacent in {}", "sliding window sum of {}", "neighbor sums in {}", "consecutive pair totals of {}"])
reg('GenerateRange', 'LIST', ['INT'], lambda n: list(range(max(1, min(n, 10)))), ["generate range to {}", "list 0 to {}", "range({})", "enumerate up to {}", "integer sequence 0..{}"])

# --- 4. Conversion & Statistics ---
reg('StringLength', 'INT', ['STR'], lambda s: len(s), ["length of string {}", "char count of {}", "len({})", "number of characters in {}", "character count of {}"])
reg('CountOccurrences', 'INT', ['STR', 'STR'], lambda s, c: s.count(c[0] if c else 'a'), ["count occurrences of {} in {}", "how many {} in {}", "frequency of {} inside {}", "tally of {} within {}", "{}.count({})"])
reg('SumOfStringDigits', 'INT', ['STR'], lambda s: sum(int(c) for c in s if c.isdigit()), ["sum of digits in string {}", "add numbers inside {}", "digit total extracted from {}", "numeric sum within {}", "sum numeric chars of {}"])
reg('IntToString', 'STR', ['INT'], lambda n: str(n), ["convert int {} to string", "str({})", "stringify {}", "number {} as text", "render {} as string"])
reg('AsciiSum', 'INT', ['STR'], lambda s: sum(ord(c) for c in s), ["sum of ascii codes in {}", "ascii total of {}", "ordinal sum of {}", "byte value sum of {}", "sum ord(c) for c in {}"])
reg('ToHex', 'STR', ['INT'], lambda n: hex(n), ["convert {} to hex", "hex({})", "hexadecimal of {}", "{} in base 16", "0x-representation of {}"])
reg('ToBinary', 'STR', ['INT'], lambda n: bin(n), ["convert {} to binary", "bin({})", "binary representation of {}", "{} in base 2", "bits of {}"])
reg('JoinList', 'STR', ['LIST'], lambda l: "".join(map(str, safe_eval_list(l))), ["join list elements {}", "concatenate list {}", "stringify and join {}", "collapse {} to string", "flatten {} as text"])
reg('ExtractDigits', 'LIST', ['STR'], lambda s: [int(c) for c in s if c.isdigit()], ["extract digits from {} as list", "numbers found in {}", "digit sequence from {}", "pull numeric chars from {}", "parse digits in {}"])
reg('CountWords', 'INT', ['STR'], lambda s: len(s.split()), ["count words in {}", "number of tokens in {}", "word count of {}", "len({}.split())", "token count of {}"])
reg('Acronym', 'STR', ['STR'], lambda s: "".join(w[0] for w in s.split() if w), ["acronym of {}", "initials of {}", "abbreviation from first letters of {}", "first-letter monogram of {}", "short form letters of {}"])
reg('MaskString', 'STR', ['STR'], lambda s: '*' * len(s), ["mask string {}", "hide content of {}", "redact {}", "censor {}", "replace {} with asterisks"])

# --- 5. Bitwise & Logic ---
reg('BitwiseAnd', 'INT', ['INT', 'INT'], lambda a, b: a & b, ["{} bitwise AND {}", "{} & {}", "AND mask {} with {}", "intersection bits {} and {}", "bitwise conjunction of {} and {}"])
reg('BitwiseOr', 'INT', ['INT', 'INT'], lambda a, b: a | b, ["{} bitwise OR {}", "{} | {}", "OR bits {} with {}", "union bits {} and {}", "bitwise disjunction of {} and {}"])
reg('BitwiseXor', 'INT', ['INT', 'INT'], lambda a, b: a ^ b, ["{} bitwise XOR {}", "{} ^ {}", "XOR {} with {}", "exclusive-or {} and {}", "bitwise difference of {} and {}"])
reg('BitwiseNot', 'INT', ['INT'], lambda a: ~a, ["bitwise NOT {}", "~{}", "complement bits of {}", "invert all bits of {}", "one's complement of {}"])
reg('LeftShift', 'INT', ['INT', 'INT'], lambda a, n: a << min(n, 8), ["left shift {} by {}", "{} << {}", "shift {} bits left {}", "multiply {} by 2^{}", "logical left shift {} {} places"])
reg('RightShift', 'INT', ['INT', 'INT'], lambda a, n: a >> min(n, 8), ["right shift {} by {}", "{} >> {}", "shift {} bits right {}", "divide {} by 2^{}", "logical right shift {} {} places"])
reg('ConditionalEven', 'INT', ['INT', 'INT', 'INT'], lambda n, a, b: a if n%2==0 else b, ["if {} is even then {} else {}", "select {} or {} based on parity of {}", "even-check {} yield {} or {}", "parity gate {} choose {} or {}", "if {} % 2 == 0 then {} else {}"])
reg('ConditionalLength', 'STR', ['STR', 'STR', 'STR', 'STR'], lambda s1, s2, a, b: a if len(s1)>len(s2) else b, ["if len({}) > len({}) then {} else {}", "length-compare {} vs {} pick {} or {}", "longer string among {} and {} selects {} else {}"])
reg('LogicalAnd', 'INT', ['INT', 'INT'], lambda a, b: 1 if a and b else 0, ["{} logical AND {}", "bool {} && {}", "both {} and {} are truthy", "conjunction of {} and {}", "1 if {} and {} else 0"])
reg('LogicalOr', 'INT', ['INT', 'INT'], lambda a, b: 1 if a or b else 0, ["{} logical OR {}", "bool {} || {}", "either {} or {} is truthy", "disjunction of {} and {}", "1 if {} or {} else 0"])
reg('PopCount', 'INT', ['INT'], lambda n: bin(n).count('1'), ["population count of {}", "hamming weight of {}", "count set bits in {}", "number of 1-bits in {}", "bit popcount {}"])

# --- 6. Geometry (Simple Int Tuples) ---
reg('EuclideanDist', 'INT', ['POINT', 'POINT'], lambda p1, p2: int(math.dist(p1, p2)), ["euclidean distance between {} and {}", "dist({}, {})", "straight-line distance from {} to {}", "L2 distance {} and {}", "math.dist({}, {})"])
reg('ManhattanDist', 'INT', ['POINT', 'POINT'], lambda p1, p2: abs(p1[0]-p2[0]) + abs(p1[1]-p2[1]), ["manhattan distance between {} and {}", "grid dist({}, {})", "city block distance {} to {}", "L1 distance {} and {}", "taxicab distance from {} to {}"])
reg('GetCoordX', 'INT', ['POINT'], lambda p: p[0], ["x coordinate of {}", "get x from {}", "horizontal component of {}", "{}.x value", "first element of point {}"])
reg('GetCoordY', 'INT', ['POINT'], lambda p: p[1], ["y coordinate of {}", "get y from {}", "vertical component of {}", "{}.y value", "second element of point {}"])
reg('CreatePoint', 'POINT', ['INT', 'INT'], lambda x, y: (x, y), ["point at ({}, {})", "coords {} {}", "make coordinate ({}, {})", "2D vector ({}, {})", "tuple ({}, {})"])
reg('ReflectX', 'POINT', ['POINT'], lambda p: (p[0], -p[1]), ["reflect {} over x axis", "flip x of {}", "mirror {} across horizontal axis", "negate y of {}", "x-axis reflection of {}"])
reg('ReflectY', 'POINT', ['POINT'], lambda p: (-p[0], p[1]), ["reflect {} over y axis", "flip y of {}", "mirror {} across vertical axis", "negate x of {}", "y-axis reflection of {}"])
reg('IsOrigin', 'INT', ['POINT'], lambda p: 1 if p==(0,0) else 0, ["is {} the origin?", "check zero point {}", "is {} at (0,0)", "origin test for {}", "does {} equal zero vector"])

# --- 7. Standard Hashing & Checksums (Real Impl) ---
reg('Adler32', 'INT', ['STR'], lambda s: zlib.adler32(s.encode()) & 0xffffffff, ["adler32 checksum of {}", "zlib adler32 {}", "adler32({})", "rolling checksum of {}", "zlib.adler32 digest of {}"])
reg('CRC32', 'INT', ['STR'], lambda s: zlib.crc32(s.encode()) & 0xffffffff, ["crc32 checksum of {}", "zlib crc32 {}", "crc32({})", "cyclic redundancy check of {}", "zlib.crc32 of {}"])
reg('SimplePosHash', 'INT', ['STR'], lambda s: sum((i+1)*ord(c) for i,c in enumerate(s)), ["positional hash of {}", "weighted sum of {}", "position-weighted ascii sum of {}", "indexed ordinal hash of {}", "linear position hash of {}"])
reg('MD5Prefix', 'STR', ['STR'], lambda s: hashlib.md5(s.encode()).hexdigest()[:8], ["first 8 chars of md5({})", "md5 prefix {}", "md5({})[:8]", "short md5 of {}", "8-char md5 digest of {}"])
reg('SHA1Prefix', 'STR', ['STR'], lambda s: hashlib.sha1(s.encode()).hexdigest()[:8], ["first 8 chars of sha1({})", "sha1 prefix {}", "sha1({})[:8]", "short sha1 of {}", "8-char sha1 digest of {}"])
reg('XorSumList', 'INT', ['LIST'], lambda l: reduce(lambda x,y: x^y, l, 0) if l else 0, ["xor sum of list {}", "bitwise xor all in {}", "fold XOR over {}", "reduce {} with XOR", "cumulative XOR of {}"])
reg('ModuloSum', 'INT', ['LIST'], lambda l: sum(l) % 256, ["sum of list {} modulo 256", "byte sum of {}", "sum({}) mod 256", "256-bounded sum of {}", "byte-range checksum of {}"])
reg('CountVowels', 'INT', ['STR'], lambda s: sum(1 for c in s if c.lower() in 'aeiou'), ["count vowels in {}", "number of vowels {}", "vowel frequency in {}", "aeiou count of {}", "how many vowels in {}"])
reg('CountConsonants', 'INT', ['STR'], lambda s: sum(1 for c in s if c.isalpha() and c.lower() not in 'aeiou'), ["count consonants in {}", "number of consonants {}", "consonant frequency in {}", "non-vowel letters in {}", "how many consonants in {}"])

# --- 9. String Encoding ---
reg('Base64Encode', 'STR', ['STR'], lambda s: base64.b64encode(s.encode()).decode(), ["base64 encode {}", "encode {} to base64", "b64encode({})", "base64 representation of {}", "encode {} as base64 string"])
reg('Base64Decode', 'STR', ['STR'], lambda s: base64.b64decode(s.encode() + b'==').decode('utf-8', errors='replace'), ["base64 decode {}", "decode base64 {}", "b64decode({})", "base64 original of {}", "recover plaintext from base64 {}"])
reg('URLEncode', 'STR', ['STR'], lambda s: urllib.parse.quote(s), ["url encode {}", "percent encode {}", "quote({})", "percent-escape {}", "make {} url-safe"])
reg('URLDecode', 'STR', ['STR'], lambda s: urllib.parse.unquote(s), ["url decode {}", "decode url {}", "unquote({})", "remove percent encoding of {}", "url-unescape {}"])
reg('HexEncode', 'STR', ['STR'], lambda s: s.encode().hex(), ["hex encode {}", "encode {} to hex bytes", "{}.encode().hex()", "byte-to-hex of {}", "hexlify {}"])
reg('HexDecode', 'STR', ['STR'], lambda s: bytes.fromhex(s).decode('utf-8', errors='replace') if all(c in '0123456789abcdefABCDEF' for c in s) and len(s)%2==0 else s, ["hex decode {}", "decode hex bytes {}", "unhexlify {}", "hex-to-ascii of {}", "bytes.fromhex({})"])
reg('ROT13', 'STR', ['STR'], lambda s: codecs.encode(s, 'rot_13'), ["rot13 of {}", "apply rot13 to {}", "caesar-13 transform {}", "rotate letters 13 of {}", "rot-13 cipher of {}"])
reg('HTMLEscape', 'STR', ['STR'], lambda s: html.escape(s), ["html escape {}", "escape html chars in {}", "html.escape({})", "sanitize html in {}", "replace & < > in {}"])

# --- 10. String Matching ---
reg('StringContains', 'INT', ['STR', 'STR'], lambda a, b: 1 if b in a else 0, ["check if {} contains {}", "does {} include {}", "is {} a substring of {}", "{} in {} (1 or 0)", "membership test {} within {}"])
reg('StringStartsWith', 'INT', ['STR', 'STR'], lambda a, b: 1 if a.startswith(b) else 0, ["check if {} starts with {}", "does {} begin with {}", "{}.startswith({})", "prefix match {} against {}", "is {} a prefix of {}"])
reg('StringEndsWith', 'INT', ['STR', 'STR'], lambda a, b: 1 if a.endswith(b) else 0, ["check if {} ends with {}", "does {} finish with {}", "{}.endswith({})", "suffix match {} against {}", "is {} a suffix of {}"])
reg('StringFind', 'INT', ['STR', 'STR'], lambda a, b: a.find(b), ["find index of {} in {}", "position of {} in {}", "{}.find({})", "first occurrence index of {} in {}", "locate {} inside {}"])
reg('StringReplaceAll', 'STR', ['STR', 'STR', 'STR'], lambda s, a, b: s.replace(a[0] if a else 'x', b[0] if b else 'y'), ["replace all {} in {} with {}", "substitute {} for {} in {}", "{}.replace({}, {})", "swap char {} with {} in {}", "character substitution {} → {} in {}"])
reg('PalindromeCheck', 'INT', ['STR'], lambda s: 1 if s == s[::-1] else 0, ["check if {} is palindrome", "is {} same backwards", "palindrome test on {}", "is {} equal to its reverse", "symmetric string check {}"])
reg('IsAlpha', 'INT', ['STR'], lambda s: 1 if s.isalpha() else 0, ["check if {} is alphabetic", "is {} all letters", "{}.isalpha()", "letters-only check on {}", "is {} purely alphabetic"])
reg('IsDigitStr', 'INT', ['STR'], lambda s: 1 if s.isdigit() else 0, ["check if {} is all digits", "is {} numeric string", "{}.isdigit()", "digits-only check on {}", "is {} a pure number string"])

# --- 11. Math Library Extensions ---
reg('FloorSqrt', 'INT', ['INT'], lambda n: int(math.floor(math.sqrt(max(0, n)))), ["floor sqrt of {}", "math.floor(sqrt({}))", "int(sqrt({}))", "largest integer not exceeding sqrt({})", "floor of square root of {}"])
reg('CeilSqrt', 'INT', ['INT'], lambda n: int(math.ceil(math.sqrt(max(0, n)))), ["ceiling sqrt of {}", "math.ceil(sqrt({}))", "smallest integer >= sqrt({})", "rounded-up sqrt of {}", "ceil of square root of {}"])
reg('Log2Int', 'INT', ['INT'], lambda n: int(math.log2(max(1, n))), ["log base 2 of {}", "int(log2({}))", "binary log of {}", "bit length floor of {}", "floor(log2({}))"])
reg('Log10Int', 'INT', ['INT'], lambda n: int(math.log10(max(1, n))), ["log base 10 of {}", "int(log10({}))", "decimal log of {}", "order of magnitude of {}", "floor(log10({}))"])
reg('Combinations', 'INT', ['INT', 'INT'], lambda n, k: math.comb(min(n,10), min(k,5)), ["combinations of {} choose {}", "C({}, {})", "math.comb({}, {})", "number of ways to choose {} from {}", "binomial coefficient C({},{})"])
reg('Permutations', 'INT', ['INT', 'INT'], lambda n, k: math.perm(min(n,8), min(k,4)), ["permutations of {} take {}", "P({}, {})", "math.perm({}, {})", "ordered arrangements of {} from {}", "P({},{}) permutation count"])
reg('DigitSum', 'INT', ['INT'], lambda n: sum(int(d) for d in str(abs(n))), ["digit sum of {}", "sum digits of {}", "add all digits of {}", "recursive digital root step of {}", "sum of individual digits in {}"])

# --- 12. NumPy Operations ---
reg('NumpyMean', 'INT', ['LIST'], lambda l: int(np.mean(safe_eval_list(l))) if l else 0, ["numpy mean of {}", "np.mean({})", "arithmetic average of {}", "expected value of {}", "mean value in {}"])
reg('NumpyStd', 'INT', ['LIST'], lambda l: int(np.std(safe_eval_list(l))) if l else 0, ["numpy std dev of {}", "np.std({})", "standard deviation of {}", "spread of values in {}", "sigma of {}"])
reg('NumpyMedian', 'INT', ['LIST'], lambda l: int(np.median(safe_eval_list(l))) if l else 0, ["numpy median of {}", "np.median({})", "middle value of {}", "50th percentile of {}", "median element in {}"])
reg('NumpyNorm', 'INT', ['LIST'], lambda l: int(np.linalg.norm(safe_eval_list(l))) if l else 0, ["numpy norm of {}", "np.linalg.norm({})", "L2 magnitude of vector {}", "euclidean norm of {}", "vector length of {}"])
reg('NumpyDot', 'INT', ['LIST', 'LIST'], lambda a, b: int(np.dot(safe_eval_list(a)[:min(len(a),len(b))], safe_eval_list(b)[:min(len(a),len(b))])), ["numpy dot product of {} and {}", "np.dot({}, {})", "inner product of {} and {}", "scalar product {} · {}", "element-wise multiply and sum {} and {}"])
reg('NumpyCumSum', 'LIST', ['LIST'], lambda l: list(map(int, np.cumsum(safe_eval_list(l)))), ["numpy cumulative sum of {}", "np.cumsum({})", "prefix sums of {}", "running total array of {}", "cumulative addition over {}"])
reg('NumpyArgmax', 'INT', ['LIST'], lambda l: int(np.argmax(safe_eval_list(l))) if l else 0, ["numpy argmax of {}", "np.argmax({})", "index of maximum in {}", "position of largest element in {}", "argmax({})"])
reg('NumpyArgmin', 'INT', ['LIST'], lambda l: int(np.argmin(safe_eval_list(l))) if l else 0, ["numpy argmin of {}", "np.argmin({})", "index of minimum in {}", "position of smallest element in {}", "argmin({})"])

# --- 13. SciPy Special Functions ---
reg('ScipyComb', 'INT', ['INT', 'INT'], lambda n, k: int(scipy.special.comb(min(n,12), min(k,6), exact=True)), ["scipy combinations C({}, {})", "scipy.comb({}, {})", "scipy.special.comb({}, {})", "exact binomial C({},{}) via scipy", "choose {} from {} exactly"])
reg('ScipyFactorial', 'INT', ['INT'], lambda n: int(scipy.special.factorial(min(n,10), exact=True)), ["scipy factorial of {}", "scipy.factorial({})", "scipy.special.factorial({})", "exact {}! via scipy", "scipy integer factorial {}"])
reg('ScipyGamma', 'INT', ['INT'], lambda n: int(scipy.special.gamma(max(1, min(n, 8)))), ["scipy gamma of {}", "Γ({})", "scipy.special.gamma({})", "gamma function at {}", "({}−1)! via gamma"])
reg('ScipyBinomPMF', 'INT', ['INT', 'INT'], lambda n, k: int(scipy.stats.binom.pmf(min(k,n), min(n,10), 0.5) * 1000), ["binomial pmf P(X={} | n={} p=0.5) x1000", "scipy.binom.pmf({}, {})", "binom probability mass {} trials {} successes x1000", "P(X={}) for Bin(n={}, p=0.5) scaled 1000"])
reg('ScipyPoissonPMF', 'INT', ['INT'], lambda mu: int(scipy.stats.poisson.pmf(min(mu,5), min(mu,5)) * 1000), ["poisson pmf at lambda={}", "scipy.poisson.pmf({})", "P(X=λ) for Poisson(λ={}) x1000", "poisson self-probability at μ={} x1000"])

# --- 8. Stack Operations (List Wrapper) ---
reg('StackPush', 'LIST', ['LIST', 'INT'], lambda l, v: l + [v], ["push {} onto stack {}", "append {} to {}", "enqueue {} into {}", "add {} to end of {}", "stack {} onto {}"])
reg('StackPop', 'LIST', ['LIST'], lambda l: l[:-1] if l else [], ["pop from stack {}", "remove last from {}", "dequeue tail of {}", "drop top of {}", "list {} minus last element"])
reg('StackPeek', 'INT', ['LIST'], lambda l: l[-1] if l else 0, ["peek top of stack {}", "last element of {}", "top of {}", "{}[-1]", "terminal element of {}"])
reg('StackClear', 'LIST', ['LIST'], lambda l: [], ["clear stack {}", "empty list {}", "reset {} to empty", "discard all items in {}", "flush stack {}"])
reg('StackDup', 'LIST', ['LIST'], lambda l: l + [l[-1]] if l else [], ["duplicate top of stack {}", "copy last in {}", "dup top of {}", "clone tail of {}", "replicate last item of {}"])
reg('StackSwap', 'LIST', ['LIST'], lambda l: l[:-2] + [l[-1], l[-2]] if len(l)>=2 else l, ["swap top two of stack {}", "exchange last 2 in {}", "transpose last pair in {}", "swap last two elements of {}", "flip last 2 in {}"])
reg('ListHead', 'INT', ['LIST'], lambda l: l[0] if l else 0, ["head of list {}", "first element of {}", "{}[0]", "front of {}", "initial element of {}"])
reg('ListTail', 'LIST', ['LIST'], lambda l: l[1:] if l else [], ["tail of list {}", "list {} without first", "{}[1:]", "drop head of {}", "rest of list {}"])

# ==========================================
# 3. AST Node Definition
# ==========================================

class ASTNode:
    def __init__(self, op_name, children):
        self.op_name = op_name
        self.children = children
        self.type = OPS[op_name]['out']

    def eval(self):
        args = []
        for child in self.children:
            val = child.eval() if hasattr(child, 'eval') else child
            if isinstance(val, tuple) and self.type == 'STR': val = str(val)
            args.append(val)
        try:
            return OPS[self.op_name]['func'](*args)
        except: return 0

    def text(self, ctx):
        args_txt = []
        for child in self.children:
            args_txt.append(child.text(ctx) if hasattr(child, 'text') else str(child))
        sym = ctx.get_sym(self.op_name)
        return f"{sym}({', '.join(args_txt)})" if sym else random.choice(OPS[self.op_name]['tmpl']).format(*args_txt)
