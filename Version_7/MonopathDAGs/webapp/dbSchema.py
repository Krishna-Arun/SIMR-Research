from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, select
Base = declarative_base()



class evals(Base):

    __tablename__= "" 
    id=Column(Integer, primary_key=True, index=True)
    username = Column(String,unique=False, index=True)
    
    