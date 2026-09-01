import factory
from django.contrib.auth import get_user_model

from pantry.models import PantryItem

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if create:
            obj.set_password(extracted or "testpass12345")
            obj.save(update_fields=["password"])


class PantryItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PantryItem

    user = factory.SubFactory(UserFactory)
    # Defaults to unresolved: PantryItem has a unique constraint on
    # (user, ingredient), and Postgres treats NULLs as distinct, so
    # factories can create many items for one user without colliding.
    ingredient = None
    raw_input = factory.Sequence(lambda n: f"mystery item {n}")
    quantity = 1
    unit = "piece"