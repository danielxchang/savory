from flask import Flask, render_template, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy
from forms import RegisterForm, LoginForm
import stripe
import os

stripe.api_key = os.environ.get('STRIPE_API_KEY')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
Bootstrap(app)

# Connect to Database
uri = os.environ.get("DATABASE_URL", "sqlite:///savory.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# Table Configurations
class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False)
    price = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class Customer(UserMixin, db.Model):
    __tablename__ = "customer"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)

# db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)

# Global variables
meals = [meal.to_dict() for meal in Meal.query.all()]
cart = {}

@login_manager.user_loader
def load_user(user_id):
    return Customer.query.get(user_id)


def get_line_items():
    line_items = []
    meal_ids = []
    for item, quantity in cart.items():
        meal = meals[item - 1]
        meal_ids.append(item)
        line_items.append({
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': meal['name']
                },
                'unit_amount_decimal': meal['price'] * 100
            },
            'quantity': quantity
        })
    return line_items, meal_ids


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if current_user.is_authenticated:
        if cart:
            session = stripe.checkout.Session.create(line_items=get_line_items()[0],
                                                     mode='payment',
                                                     success_url='http://127.0.0.1:4242/order/success',
                                                     cancel_url='http://127.0.0.1:4242/cancel')
            return redirect(session.url, code=303)
        else:
            return redirect(url_for('home'))
    else:
        flash("You must be signed in to checkout. Please log in!")
        return redirect(url_for('login'))


@app.route('/order/success')
def order_success():
    cart.clear()
    return render_template('success.html')


@app.route('/cancel')
def cancel():
    return redirect(url_for('shopping_cart'))


@app.route("/update-cart/<int:meal_id>")
def add_to_cart(meal_id):
    if cart.get(meal_id):
        cart[meal_id] += 1
    else:
        cart[meal_id] = 1
    return redirect(url_for('home'))


@app.route("/shopping-cart")
def shopping_cart():
    line_items, meal_ids = get_line_items()
    total = 0
    for item in line_items:
        total += item['price_data']['unit_amount_decimal'] / 100 * float(item['quantity'])
    return render_template('shopping_cart.html',
                           total_price=round(total, 2),
                           line_items=line_items,
                           round=round,
                           enumerate=enumerate,
                           meal_ids=meal_ids,
                           float=float)


@app.route("/update-quantity/<int:item_idx>", methods=['GET', 'POST'])
def update_quantity(item_idx):
    cart_idx = list(cart.keys())[item_idx]
    if request.method == 'GET':
        cart.pop(cart_idx)
    else:
        quantity = int(request.form[f'quantity-{item_idx}'])
        if quantity > 0:
            cart[cart_idx] = request.form[f'quantity-{item_idx}']
        else:
            cart.pop(cart_idx)

    return redirect(url_for('shopping_cart'))


@app.route("/")
def home():
    return render_template('index.html', meals=meals)


@app.route("/about")
def about():
    return render_template('about.html')


@app.route("/contact")
def contact():
    return render_template('contact.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    else:
        register_form = RegisterForm()
        if register_form.validate_on_submit():
            email = register_form.email.data
            if Customer.query.filter_by(email=email).first():
                flash("You've already signed up with that email, log in instead!")
                return redirect(url_for('login'))
            else:
                new_customer = Customer(
                    name=register_form.name.data,
                    email=email,
                    password=generate_password_hash(register_form.password.data, method='pbkdf2:sha256', salt_length=8)
                )
                db.session.add(new_customer)
                db.session.commit()

                login_user(new_customer)
                return redirect(url_for('shopping_cart')) if cart else redirect(url_for('home'))
        return render_template("register.html", form=register_form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    else:
        login_form = LoginForm()
        if login_form.validate_on_submit():
            if customer := Customer.query.filter_by(email=login_form.email.data).first():
                if check_password_hash(customer.password, login_form.password.data):
                    login_user(customer)
                    return redirect(url_for('shopping_cart')) if cart else redirect(url_for('home'))
                else:
                    flash("Password incorrect. Please try again.")
                    return redirect(url_for('login'))
            else:
                flash("That email does not exist. Please try again.")
                return redirect(url_for('login'))
        return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    cart.clear()
    return redirect(url_for('home'))


if __name__ == "__main__":
    app.run(port=4242, debug=True)
