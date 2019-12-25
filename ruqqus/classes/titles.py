from sqlalchemy import *

from ruqqus.helpers.base36 import *
from ruqqus.helpers.security import *
from ruqqus.helpers.lazy import lazy
from .votes import Vote
from .alts import Alt
from ruqqus.__main__ import Base, db, cache

class Title(Base):

    __tablename__="titles"
    id=Column(Integer, primary_key=True)
    is_before=Column(Boolean, default=True)
    text=Column(String(64))
    qualification_expr = Column(String(256))
    requirement_string = Column(String(512))
    color=Column(String(6))

    def assign_to(user):

        user.title=self.id

        db.add(user)
        db.commit()

    def check_eligibility(user):

        return bool(eval(self.qualification_expr, {}, {"v":user, "user":user}))
