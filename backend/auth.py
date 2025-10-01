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
from datetime import timedelta, datetime
from typing import Annotated
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel
from starlette import status
from jose import jwt, JWTError
from passlib.context import CryptContext

from database import db_dependency
from models import Users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)

SECRET_KEY = '574m20j76877m2345m087n446465h45498210t4551hj9qpms'
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 60

bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
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
    try:
        blacklisted_tokens.add(token)
        return {"msg": "Successfully logged out"}
    except Exception as e:
        logger.exception("Logout failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    create_user_request: CreateUserRequest,
    db: db_dependency
):
    try:
        # Check if user already exists
        existing_user = db.query(Users).filter(Users.email == create_user_request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        # Create new user
        new_user = Users(
            email=create_user_request.email,
            password_hash=bcrypt_context.hash(create_user_request.password[:72])
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {"msg": "User created successfully", "email": new_user.email, "id": new_user.id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("User creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User creation failed: {str(e)}"
        )

@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: db_dependency
):
    try:
        user = authenticate_user(form_data.username, form_data.password, db)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        access_token = create_access_token(user.email, user.id, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Login failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )
        
def authenticate_user(email: str, password: str, db):
    try:
        user = db.query(Users).filter(Users.email == email).first()
        if not user:
            return False
        if not bcrypt_context.verify(password[:72], user.password_hash):
            return False
        return user
    except Exception as e:
        logger.exception("Authentication failed")
        return False

def create_access_token(email: str, user_id: int, expires_delta: timedelta):
    try:
        payload = {
            "sub": email,
            "id": user_id,
            "exp": datetime.utcnow() + expires_delta
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    except Exception as e:
        logger.exception("Token creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token creation failed: {str(e)}"
        )

async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    if token in blacklisted_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please login again."
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: int = payload.get("id")
        if email is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing required fields"
            )
        return {"email": email, "id": user_id}
    except JWTError as e:
        logger.exception("JWT decoding error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}"
        )
    except Exception as e:
        logger.exception("Unexpected error in token validation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token validation failed: {str(e)}"
        )

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
