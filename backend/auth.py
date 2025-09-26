from datetime import timedelta, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette import status
from database import SessionLocal, db_dependency
from models import Users
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)

SECRET_KEY = '574m20j76877m2345m087n446465h45498210t4551hj9qpms'
ALGORITHM =  'HS256'

bcrypt_context = CryptContext(schemes=['bcrypt'],deprecated='auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/login')

class CreateUserRequest(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str


blacklisted_tokens = set()

@router.post("/logout")
async def logout(token: Annotated[str, Depends(oauth2_bearer)]):
    blacklisted_tokens.add(token)
    return {"msg": "Successfully logged out"}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def created_user(db: db_dependency, create_user_request: CreateUserRequest):
    existing_user = db.query(Users).filter(Users.email == create_user_request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Create new user
    create_user_model = Users(
        email=create_user_request.email,
        password_hash=bcrypt_context.hash(create_user_request.password),
    )
    db.add(create_user_model)
    db.commit()
    db.refresh(create_user_model) 

@router.post("/login",response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                                 db:db_dependency):
    user = authenticate_user(form_data.username, form_data.password,db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not validate user')
    token = create_access_token(user.email,user.id,timedelta(minutes=60))

    return {'access_token':token, 'token_type':'bearer'}

def authenticate_user(email:str , password:str,db):
    user  = db.query(Users).filter(Users.email==email).first()
    if not user:
        return False
    if not bcrypt_context.verify(password,user.password_hash):
        return False
    return user 

def create_access_token(email:str, user_id : int , expires_delta : timedelta):
    encode = {'sub':email,'id':user_id}
    expires = datetime.utcnow() + expires_delta
    encode.update({'exp':expires})
    return jwt.encode(encode, SECRET_KEY , algorithm = ALGORITHM)

async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    if token in blacklisted_tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked. Please login again.")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get('sub')
        user_id: int = payload.get('id')
        if email is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Could not validate user.')
        return {'email': email, 'id': user_id}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not validate user.')
