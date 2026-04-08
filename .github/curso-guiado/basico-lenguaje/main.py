def tipos_basicos():
    s= "hello"
    print(s)
    x = 10 * 100
    print(x)
    x = 2 ** 4
    print(x)
    x = [1,2,3] 
    print(x)
    x1 = ["a1", "a2", "a3"]
    y1 = ["a1", "a2", "a3"]
    print(x)
    x = ['{"key1": [{ "obj1": {"objId": 1, "objName":"Mark"}], "key2":[]}']
    print(x)
    print(True)
    print(True + True)
    print(True == 1)
    print(x1 + y1)
    print(x1 == y1)
    print((x1 == y1) + (x1 != y1))
    print((x1 == y1) + (x1 == y1))
    # LIST — equivalente a List<T>, pero sin tipo
    fruits = ["apple", "banana", "cherry"]
    fruits.append("date")
    print(fruits[0])
    print(fruits[-1])
    print(fruits[1:3])
    user = {"name": "Maria", "age": 47}
    print(user["name"])
    print(user.get("email"))
    print(user.get("email", "no-email"))      

    # TUPLE — inmutable, similar a ValueTuple en C#
    point = (10, 20)
    x, y = point # Unpacking — muy usado en Python
    print(x, "-",y)  

    # LIST — equivalente a List<T>, pero sin tipo
    dups = [1, 2, 3, 2, 1]
    print(dups)

    # SET — equivalente a HashSet<T>
    unique = {1, 2, 3, 2, 1}
    print(unique)

def add(a: int, b: int) -> int:
    return a + b

def min_max(numbers):
    return min(numbers), max(numbers)

def add_item(item, cart=[]):  # cart=[] se evalúa UNA SOLA VEZ al definir la función
    cart.append(item)
    return cart

def add_item_correct(item, cart=None):
    if cart is None:
        cart = []   # Nueva lista en cada llamada
    cart.append(item)
    return cart

def log(*args, **kwargs):
    print(args)  # Tuple de posicionales
    print(kwargs) # Dict de nombrados

def f(x, data={}):
    data[x] = x * 2
    return data



tipos_basicos()
print(add(5,4))
low, hight = min_max([3,1,5,7,2,9])
print(low, "-", hight)

print(add_item("banana"))
print(add_item("mango"))
print(add_item("cherry"))

print(add_item_correct(1))
print(add_item_correct(2))
print(add_item_correct(3))

log("error", "db_timeout","request_timeout", severity="high", code=500)

numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# C#: numbers.Where(n => n % 2 == 0).Select(n => n * n).ToList()
squares_of_evens = [n * n for n in numbers if n % 2 == 0]
# [4, 16, 36, 64, 100]
print(squares_of_evens)

word_lenghts = {word: len(word) for word in ["apple", "banana", "mango", "kiwi"]}
print(word_lenghts)

unique_lenghts = {len(word) for word in ["apple", "banana", "mango", "kiwi"]}
print(unique_lenghts)

print("lens:",{word for word in word_lenghts.values()})

# Generator expression — lazy, como IEnumerable sin ToList()
# NO crea la lista en memoria, produce valores uno a uno
gen = (n * n for n in range(1_000_000))   # Instantáneo — no calcula nada todavía
next(gen)  # 0  ← recién ahora calcula el primero
print(next(gen))
print(next(gen))
print(next(gen))
print(next(gen))

while next(gen):
    g = next(gen) 
    if  g > 1000:
        break
    print(g)
n = "str"

print(n.upper())
print(n.startswith("s"))
print(f("a"))
print(f("b"))

strs = [n.upper() for n in ["mario","javier","cabrera", "chang" ] if n.startswith("m")]
print(strs)

users = []
template = {"tags": []} # lista compartida
for name in ["Alice", "Bob", "Carol"]:
    u = template
    u["name"] = name # type: ignore
    users.append(u)
    # users.append({"name": name, "tags": []})
print(users)
