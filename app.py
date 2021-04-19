from functools import wraps

import connexion
from flask import request, abort
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import time
import jwt

SECRET = 'SECRETSTUFF'
APIKEY = 'PAYMENT_APIKEY'


def has_role(arg):
    def has_role_inner(fn):
        @wraps(fn)
        def decode_view(*args, **kwargs):
            try:
                headers = request.headers
                if 'AUTHORIZATION' in headers:
                    token = headers['AUTHORIZATION'].split(' ')[1]
                    decoded_token = decode_token(token)
                    if 'admin' in decoded_token:
                        return fn(*args, **kwargs)
                    for role in arg:
                        if role in decoded_token['roles']:
                            return fn(*args, **kwargs)
                    abort(404)
                return fn(*args, **kwargs)
            except Exception as e:
                abort(401)

        return decode_view

    return has_role_inner


def decode_token(token):
    return jwt.decode(token, SECRET, algorithms='HS256')


def hello_world(name: str) -> str:
    return 'Hello World! {name}'.format(name=name)


def find_all_transactions():
    transactions = Transaction.query.all()
    if transactions:
        return transactions_to_json_array(transactions), 200
    else:
        return {'message': 'error'}, 404


def find_user_transactions(user_id):
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    if transactions:
        return transactions_to_json_array(transactions), 200
    else:
        return {'message': '{} not found'.format(user_id)}, 404


@has_role(['invoice'])
def transaction_details(transaction_id):
    transaction = Transaction.query.filter_by(id=transaction_id).first()
    if transaction:
        return transaction_to_json(transaction), 200
    else:
        return {'message': 'error not found'}, 404


def edit_transaction(transaction_id, transaction_body):
    transaction = Transaction.query.filter_by(id=transaction_id).first()
    if transaction:
        transaction.user_id = transaction_body['user_id']
        transaction.amount = transaction_body['amount']
        transaction.completed = transaction_body['completed']
        transaction.date = datetime.now()
        db.session.add(transaction)
        db.session.commit()
        return transaction_to_json(transaction), 200
    else:
        return {'message': 'error not found'}, 404


def save_transaction(transaction_body):
    transaction = Transaction(date=datetime.now(),
                              amount=transaction_body['amount'],
                              user=UserPayments.query.filter_by(id=transaction_body['user_id']).first(),
                              completed=transaction_body['completed'])
    db.session.add(transaction)
    db.session.commit()


def cart_payment_status(transaction_id):
    transaction = db.session.query(Transaction).filter_by(id=transaction_id).first()
    if transaction:
        return transaction.completed
    else:
        return {'message': 'error not found'}, 404


def rent_payment_status(transaction_id):
    transaction = db.session.query(Transaction).filter_by(id=transaction_id).first()
    if transaction:
        return transaction.completed
    else:
        return {'message': 'error not found'}, 404


def find_all_user_payment_methods(user_id):
    payment_methods = PaymentMethods.query.filter_by(user_id=user_id).all()
    if payment_methods:
        return payment_methods_to_json_array(payment_methods), 200
    else:
        return {'message': 'error not found'}, 404


def save_user_payment_method(user_id, user_payment_method):
    user = UserPayments.query.filter_by(id=user_id).first()
    if not user:
        user = UserPayments(id=user_id, funds=0)
        db.session.add(user)
        return insert_payment_method(user_payment_method, user_id), 200
    else:
        return insert_payment_method(user_payment_method, user_id), 200


def insert_payment_method(user_payment_method, user_id):
    payment_method = {}
    if user_payment_method['type'] == 'credit_cards':
        payment_method = CreditCards(user_id=user_id,
                                     cc_number=user_payment_method['method']['cc_number'],
                                     cvc=user_payment_method['method']['cvc'],
                                     valid_month=user_payment_method['method']['valid_month'],
                                     valid_year=user_payment_method['method']['valid_year'],
                                     card_type=user_payment_method['method']['card_type'])
        if not check_if_credit_card_exists(payment_method):
            db.session.add(payment_method)
        else:
            return {'message': 'Already exists'}, 409
    elif user_payment_method['type'] == 'paypal':
        payment_method = PayPal(email=user_payment_method['method']['email'], user_id=user_id)
        payment_method.set_password(user_payment_method['method']['password'])
        if not check_if_paypal_exists(user_id, user_payment_method['method']['email'],
                                      user_payment_method['method']['password']):
            db.session.add(payment_method)
        else:
            return {'message': 'Already exists'}, 409
    db.session.commit()

    return payment_method_to_json(payment_method), 200


def check_if_credit_card_exists(payment_method):
    curr_card_type = CardType.master
    if payment_method.card_type == "visa":
        curr_card_type = CardType.visa

    credit_cards = CreditCards.query.filter_by(user_id=payment_method.user_id,
                                               cc_number=payment_method.cc_number,
                                               cvc=payment_method.cvc,
                                               valid_month=payment_method.valid_month,
                                               valid_year=payment_method.valid_year,
                                               card_type=curr_card_type).count()
    if credit_cards > 0:
        return True
    return False


def check_if_paypal_exists(user_id, email, password):
    paypals = PayPal.query.filter_by(user_id=user_id)

    for paypal in paypals:
        if paypal.email == email and paypal.check_password(password):
            return True
    return False


def find_user_payment_method_by_id(method_id):
    payment_method = PaymentMethods.query.filter_by(id=method_id).first()
    if payment_method:
        return payment_method_to_json(payment_method), 200
    else:
        return {'message': 'error not found'}, 404


def delete_user_payment_method(method_id):
    payment_method = PaymentMethods.query.filter_by(id=method_id).first()
    if payment_method:
        db.session.delete(payment_method)
        db.session.commit()
        return {'message': 'successfully deleted'}, 200
    else:
        return {'message': 'error not found'}, 404


# Only for testing purposes
# Generate token
def auth_microservice(auth_body_microservice):
    apikey = auth_body_microservice['apikey']

    if apikey == 'PAYMENT_APIKEY':
        roles = ['invoice', 'shopping_cart']
        sub = 'payment'

    user = {"id": 0}

    timestamp = int(time.time())
    payload = {
        "iss": 'my app',
        "iat": int(timestamp),
        "exp": int(timestamp + 600000),
        "sub": sub,
        "roles": roles,
        "user_details": user
    }
    encoded = jwt.encode(payload, SECRET, algorithm="HS256")
    return encoded


@has_role(['shopping_cart'])
def cart_pay(amount):
    # TODO apply discount to amount (call to discount Microservice)
    discounted_amount = amount
    return pay(discounted_amount)


@has_role(['shopping_cart'])
def rent_pay(amount):
    # TODO apply discount to amount (call to discount Microservice)
    discounted_amount = amount
    return pay(discounted_amount)


@has_role(['shopping_cart'])
def parking_pay(amount):
    # TODO apply discount to amount (call to discount Microservice)
    discounted_amount = amount
    return pay(discounted_amount)


def pay(amount):
    headers = request.headers
    if 'AUTHORIZATION' in headers:
        token = headers['AUTHORIZATION'].split(' ')[1]
        decoded_token = decode_token(token)
        user_id = decoded_token['user_details']['id']
        transaction = Transaction(date=datetime.now(),
                                  amount=amount['amount'],
                                  user=UserPayments.query.filter_by(id=user_id).first(),
                                  completed=True)
        db.session.add(transaction)
        db.session.commit()
        return transaction_to_json(transaction), 200
    else:
        return {'message': 'pay was not successful'}, 400


connexion_app = connexion.App(__name__, specification_dir="./config/")
app = connexion_app.app
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
connexion_app.add_api("api.yml")

from models import PaymentMethods, UserPayments, Transaction, PayPal, CreditCards, MethodType, CardType
from functions import *

if __name__ == '__main__':
    # pp = PayPal(email="name@gmail.com", user_id=0)
    # pp.set_password("Chronic")
    # cc = CreditCards(user_id=0,
    #                  cc_number="4248378499284623",
    #                  cvc="361",
    #                  valid_month="06",
    #                  valid_year="23",
    #                  card_type=CardType.visa,
    #                  )
    # db.session.add(cc)
    # db.session.add(pp)
    # db.session.commit()
    # pms = PaymentMethods.query.filter_by(user_id=0).all()
    # print(pms)
    connexion_app.run(port=5000, debug=True)
