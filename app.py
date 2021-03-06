import os
from os import environ as env
from dotenv import load_dotenv
from flask_moment import Moment

load_dotenv()

envUser = env['DBUSER']
envPass = env['DBPASS']

from flask import Flask, render_template, request, flash, redirect, session, g
from flask_debugtoolbar import DebugToolbarExtension
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate

from forms import UserAddForm, LoginForm, MessageForm, UserEditForm
from models import db, connect_db, User, Message, Likes

CURR_USER_KEY = "curr_user"

app = Flask(__name__)

moment = Moment(app)

migrate = Migrate(app, db)

# Get DB_URI from environ variable (useful for production/testing) or,
# if not set there, use development local db.
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('DATABASE_URL', f'postgresql://{envUser}:{envPass}@tonyalvarez-twitter-clone-webapp-db-1.postgres.database.azure.com:5432/warbler'))
# app.config['SQLALCHEMY_DATABASE_URI'] = (
#     os.environ.get('DATABASE_URL', 'postgresql:///warbler'))

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', "it's a secret")
toolbar = DebugToolbarExtension(app)

connect_db(app)


# Set IDs to IDs.length so new objects do not throw primary key errors
db.engine.execute("SELECT setval('users_id_seq', MAX(id)) FROM users;")
db.engine.execute("SELECT setval('messages_id_seq', MAX(id)) FROM messages;")
db.engine.execute("SELECT setval('likes_id_seq', MAX(id)) FROM likes;")

##############################################################################
# User signup/login/logout


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""

    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])

    else:
        g.user = None


def do_login(user):
    """Log in user."""

    session[CURR_USER_KEY] = user.id


def do_logout():
    """Logout user."""

    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]
        

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html")


@app.route('/signup', methods=["GET", "POST"])
def signup():
    """Handle user signup.

    Create new user and add to DB. Redirect to home page.

    If form not valid, present form.

    If the there already is a user with that username: flash message
    and re-present form.
    """

    # import pdb
    # pdb.set_trace()

    form = UserAddForm()

    if form.validate_on_submit():
        try:
            user = User.signup(
                username=form.username.data,
                password=form.password.data,
                email=form.email.data,
                image_url=form.image_url.data or User.image_url.default.arg,
            )

            db.session.commit()

        except IntegrityError:
            print(IntegrityError)
            flash("User already exists", 'danger')
            return render_template('users/signup.html', form=form)

        do_login(user)

        return redirect("/")

    else:
        return render_template('users/signup.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    """Handle user login."""
    
    # if user is already logged in and user visits
    # login endpoint, redirect to "/"
    if g.user:
        return redirect('/')

    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(form.username.data,
                                 form.password.data)

        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            return redirect("/")

        flash("Invalid credentials.", 'danger')

    return render_template('users/login.html', form=form)


@app.route('/logout')
def logout():
    """Handle logout of user."""

    # call the do_logout() method here
    do_logout()

    # flash the user to confirm that they have been logged out
    if g.user:
        flash("You have been logged out.", 'danger')

    # redirect them back to index page
    return redirect("/")


##############################################################################
# General user routes:


@app.route('/users')
def list_users():
    """Page with listing of users.

    Can take a 'q' param in querystring to search by that username.
    """

    search = request.args.get('q')

    if not search:
        users = User.query.all()
    else:
        users = User.query.filter(User.username.like(f"%{search}%")).all()

    return render_template('users/index.html', users=users)


@app.route('/users/<int:user_id>')
def users_show(user_id):
    """Show user profile."""

    user = User.query.get_or_404(user_id)

    # snagging messages in order from the database;
    # user.messages won't be in order by default
    messages = (Message
                .query
                .filter(Message.user_id == user_id)
                .order_by(Message.timestamp.desc())
                .limit(100)
                .all())
    likes = (
        Likes
        .query
        .filter(Likes.user_id == user_id)
        .all())
    return render_template('users/show.html', user=user, messages=messages, likes=likes)


@app.route('/users/<int:user_id>/following')
def show_following(user_id):
    """Show list of people this user is following."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    return render_template('users/following.html', user=user)


@app.route('/users/<int:user_id>/followers')
def users_followers(user_id):
    """Show list of followers of this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    
    return render_template('users/followers.html', user=user)


@app.route('/users/follow/<int:follow_id>', methods=['GET','POST'])
def add_follow(follow_id):
    """Add a follow for the currently-logged-in user."""
    
    if not g.user or request.method == 'GET':
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get_or_404(follow_id)
    g.user.following.append(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/stop-following/<int:follow_id>', methods=['POST'])
def stop_following(follow_id):
    """Have currently-logged-in-user stop following this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get_or_404(follow_id)
    g.user.following.remove(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/profile', methods=["GET", "POST"])
def profile():
    """Update profile for current user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(g.user.id)
    
    form = UserEditForm()
    
    if form.validate_on_submit():
        # query the current logged in user
        
        # authentice the user
        valid_user = User.authenticate(user.username, form.password.data)

        # if the password is valid, commit the changes
        # to the database and redirect to the user's page

        if valid_user:
            user.username = form.username.data
            user.email = form.email.data
            if form.image_url.data:
                user.image_url = form.image_url.data
            if form.header_image_url.data:
                user.header_image_url = form.header_image_url.data
            user.bio = form.bio.data
            user.location = form.location.data

            db.session.commit()
            return redirect(f"/users/{g.user.id}")
        
        # if not, de-commit the changes and 
        # redirect to home
        else:
            db.session.rollback()
            flash("Incorrect password", "danger")
            return redirect("/")

    else:
        return render_template('users/edit.html', user=user, form=form)


@app.route('/users/delete', methods=["GET","POST"])
def delete_user():
    """Delete user."""

    if not g.user or request.method == 'GET':
        flash("Access unauthorized.", "danger")
        return redirect("/")

    do_logout()

    db.session.delete(g.user)
    db.session.commit()

    return redirect("/signup")


##############################################################################
# Likes routes:
@app.route('/users/<int:user_id>/likes')
def show_likes(user_id):
    """
    Show the messages the user has liked.
    User must be logged in to view another user's likes.
    """
    
    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    likes = (
        Likes
        .query
        .filter(Likes.user_id == user_id)
        .all())
    
    all_messages = [l.message_id for l in likes]
    
    messages = (
        Message
        .query
        .filter(Message.id.in_(all_messages))
        .order_by(Message.timestamp.desc())
        .all())
    
    return render_template("likes/show.html", messages=messages)
        

@app.route('/users/add_like/<int:message_id>', methods=["GET", "POST"])
def add_like(message_id):
    """
    Like a message.
    Users should not be able to like their own messages.
    Anon users should not be able to like any messages.
    """

    # prevent anon user from accessing endpoint
    # prevent g.user from entering endpoint in url
    if not g.user or request.method == 'GET':
        flash("Access unauthorized.", "danger")
        return redirect("/")

    # query the message instance
    msg = Message.query.get(message_id)
    
    # check that the liked message is NOT owned by g.user
    if msg.user_id != g.user.id:
        
        # create a new Like instance
        new_like = Likes(
            user_id=g.user.id,
            message_id=message_id
        )

        # add to session
        db.session.add(new_like)

        # commit to database
        db.session.commit()
    
    # if liked message DOES match g.user, show flash error
    else:
        flash("Access unauthorized.", "danger")

    return redirect("/")


@app.route('/users/remove_like/<int:message_id>', methods=["GET", "POST"])
def remove_like(message_id):
    """
    Un-Like a message.
    Users should not be able to un-like their own messages.
    Anon users should not be able to un-like any messages.
    """

    if not g.user or request.method == 'GET':
        flash("Access unauthorized.", "danger")
        return redirect("/")

    like = Likes.query.filter_by(message_id=message_id).first()
    
    if like.user_id == g.user.id:
        db.session.delete(like)
    
        db.session.commit()
        
    else:
        flash("You can't unlike your own post!", "danger")

    return redirect("/")

##############################################################################
# Messages routes:

@app.route('/messages/new', methods=["GET", "POST"])
def messages_add():
    """Add a message:

    Show form if GET. If valid, update message and redirect to user page.
    """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = MessageForm()

    if form.validate_on_submit():
        msg = Message(text=form.text.data, user_id=g.user.id)
        
        g.user.messages.append(msg)
        db.session.commit()

        return redirect(f"/users/{g.user.id}")

    return render_template('messages/new.html', form=form)


@app.route('/messages/<int:message_id>', methods=["GET"])
def messages_show(message_id):
    """Show a message."""
    
    msg = Message.query.get(message_id)

    if msg:
        return render_template('messages/show.html', message=msg)

    flash("Access unauthorized.", "danger")
    return redirect("/")


@app.route('/messages/<int:message_id>/delete', methods=["GET", "POST"])
def messages_destroy(message_id):
    """Delete a message only if it belongs to the user."""

    if not g.user or request.method == 'GET':
        flash("Access unauthorized.", "danger")
        return redirect("/")
    
    msg = Message.query.get(message_id)
    
    if msg.user_id == g.user.id:
        db.session.delete(msg)
        db.session.commit()
        
    else:
        flash("Access unauthorized.", "danger")        
    
    return redirect(f"/users/{g.user.id}")


##############################################################################
# Homepage and error pages


@app.route('/')
def homepage():
    """Show homepage:

    - anon users: no messages
    - logged in: 100 most recent messages of followed_users
    """

    if g.user:
        # create a list of all ids that our user follows
        following = [f.id for f in g.user.following]
    
        # append our user's id as well into this list
        following.append(g.user.id)
    
        # query all messages that match the ids in our following list
        messages = (Message
                    .query
                    .filter(Message.user_id.in_(following))
                    .order_by(Message.timestamp.desc())
                    .limit(100)
                    .all())
    
        # query all likes of that match our g.user
        all_likes = Likes.query.filter_by(user_id=g.user.id).all()
    
        # put all ids from likes into an arr
        # we will eventually pass this to jinja
        likes = [l.message_id for l in all_likes]

        return render_template('home.html', messages=messages, likes=likes)

    else:
        return render_template('home-anon.html')


##############################################################################
# Turn off all caching in Flask
#   (useful for dev; in production, this kind of stuff is typically
#   handled elsewhere)
#
# https://stackoverflow.com/questions/34066804/disabling-caching-in-flask

@app.after_request
def add_header(req):
    """Add non-caching headers on every request."""

    req.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    req.headers["Pragma"] = "no-cache"
    req.headers["Expires"] = "0"
    req.headers['Cache-Control'] = 'public, max-age=0'
    return req
