from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Protocol


# C# interface IRepository -> Python Protocol (structural typing)
class UserRepository(Protocol):
    def get_by_id(self, user_id: int) -> dict | None:
        ...


# C# abstract class -> Python ABC (explicit contract)
class Logger(ABC):
    @abstractmethod
    def info(self, message: str) -> None:
        pass


class ConsoleLogger(Logger):
    def info(self, message: str) -> None:
        print(f"[INFO] {message}")


@dataclass
class User:
    id: int
    name: str
    is_active: bool = True

@dataclass
class Product:
    id: int
    name: str
    value: float

@dataclass
class Order:
    order_id: int
    cart: dict[int, int]  


class InMemoryUserRepository:
    def __init__(self, users: list[User]):
        # Important: no mutable default in signature; state injected from outside
        self._by_id = {u.id: {"id": u.id, "name": u.name, "is_active": u.is_active} for u in users}

    def get_by_id(self, user_id: int) -> dict | None:
        return self._by_id.get(user_id)

class UserService:
    def __init__(self, repo: UserRepository, logger: Logger):
        self._repo = repo
        self._logger = logger

    @classmethod
    def with_defaults(cls) -> "UserService":
        repo = InMemoryUserRepository([User(1, "Ana"), User(2, "Luis", is_active=False)])
        logger = ConsoleLogger()
        return cls(repo, logger)

    def get_active_user_name(self, user_id: int) -> str:
        user = self._repo.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        if not user["is_active"]:
            raise ValueError(f"User {user_id} is inactive")
        self._logger.info(f"Resolved active user {user_id}")
        return user["name"]

class OrderRepository(Protocol):
    def get_order_by_id(self, order_id: int) -> Order | None:
        ...

class InventoryRepository:
    def __init__(self) -> None:
        self._products = {
            1: Product(1, "Tenis", 10.5),
            2: Product(2, "Camisa", 4.99),
            3: Product(3, "Pantalon", 6.79),
        }

    def get_product_by_id(self, product_id: int) -> Product | None:
        return self._products.get(product_id)

class InMemoryOrderRepository:
    def __init__(self, orders: list[Order]) -> None:
        self._orders_by_id = {order.order_id: order for order in orders}
    
    def get_order_by_id(self, order_id: int) -> Order | None:
        return self._orders_by_id.get(order_id)

class TaxCalculator(ABC):  
    _tax_rate = .07  
    @abstractmethod
    def apply_tax(self, amount: float) -> float:
        pass

class OrderTaxCalculator(TaxCalculator):
    def __init__(self) -> None:
        super().__init__()
    def apply_tax(self, amount: float) -> float:
        return amount + (amount * super()._tax_rate)

class OrderService:
    def __init__(self, order_repo: OrderRepository, logger: Logger, tax_calculator: OrderTaxCalculator, inventory_repository: InventoryRepository):
        self._logger = logger
        self._order_repo = order_repo
        self._tax_calculator = tax_calculator
        self._inventory_repo = inventory_repository
    
    @classmethod
    def with_defaults(cls) -> "OrderService":
        order_list = [Order(1, {1: 1, 2: 3}), Order(2, {3: 1, 4: 3}), Order(3, {5: 1, 2: 3})]
        repo = InMemoryOrderRepository(order_list)
        tax_calculator = OrderTaxCalculator()
        logger = ConsoleLogger()
        return cls(repo, logger, tax_calculator, InventoryRepository())

    def get_total(self, order_id: int) -> float |None:
        order = self._order_repo.get_order_by_id(order_id)
        if order is None:
            return None            
        cart = order.cart
        subtotals = [self.calculate_subtotal(key, cart[key]) for key in cart]
        total = 0
        for sub in subtotals:
            total += sub
        return total
    
    def calculate_subtotal(self, product_id: int, quantity: int) -> float:
        product = self._inventory_repo.get_product_by_id(product_id)
        if product is None:
            raise ValueError(f"Product with id: {product_id} not found")
        return product.value * quantity

    def get_total_with_tax(self, order_id: int) -> float:
        total = self.get_total(order_id)
        if total is None:
            raise ValueError(f"Order with id: {order_id} does not exist.")
        if total < 0:
            raise ValueError(f"Negative value in Total: {total}")
        final = self._tax_calculator.apply_tax(total)
        self._logger.info(f"Order Total: ${final:.2f}")
        return final
        



if __name__ == "__main__":
    # service = UserService.with_defaults()
    # print(service.get_active_user_name(1))  # Ana
    # print(service.get_active_user_name(2))  # ValueError inactive
    # print(service.get_active_user_name(3))  # ValueError not found

    order_service = OrderService.with_defaults()
    total = order_service.get_total_with_tax(1)
    print(f"total a pagar: ${total:.2f}")
