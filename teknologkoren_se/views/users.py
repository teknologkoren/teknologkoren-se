import random
from string import ascii_letters, digits
from flask import (Blueprint, request, redirect, render_template, url_for,
                   abort, flash)
from flask_login import current_user, login_user, logout_user, login_required
from playhouse.flask_utils import get_object_or_404
from itsdangerous import SignatureExpired
from teknologkoren_se import login_manager
from teknologkoren_se.forms import (LoginForm, AddUserForm, PasswordForm,
                                    ExistingEmailForm)
from teknologkoren_se.models import User
from teknologkoren_se.util import send_email, ts


mod = Blueprint('users', __name__)


@login_manager.user_loader
def load_user(userid):
    """Tell flask-login how to get logged in user."""
    return User.get(User.id == userid)


@mod.route('/login/', methods=['GET', 'POST'])
def login():
    """Show login page and form.

    Not showing which field was wrong if any is intentional. Usernames
    and passwords only represent anything when used in combination
    (http://ux.stackexchange.com/a/13523).
    """
    form = LoginForm(request.form)

    if current_user.is_authenticated:
        return form.redirect('intranet.index')

    if form.validate_on_submit():
        user = form.user
        login_user(user, remember=form.remember.data)
        return form.redirect('intranet.index')
    elif form.is_submitted():
        flash("Sorry, your email address or password was incorrect.", 'error')

    return render_template('users/login.html', form=form)


@mod.route('/logout/')
def logout():
    """Logout user (if logged in) and redirect to main page."""
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for('blog.index'))


@mod.route('/adduser/', methods=['GET', 'POST'])
@login_required
def adduser():
    """Add a user."""
    form = AddUserForm(request.form)
    if form.validate_on_submit():
        password = ''.join(
                random.choice(ascii_letters + digits) for _ in range(30))

        User.create(
                email=form.email.data,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                phone=form.phone.data,
                password=password,
                )

        return redirect('intranet.index')

    return render_template('users/adduser.html', form=form)


def verify_email(user, email):
    """Create an email verification email.

    The user id and the requested email address is hashed and included as a
    token in a link referring to the verification page. The link is sent to the
    requested email address.

    The token is timestamped, when verifying we can check the age.
    """
    token = ts.dumps([user.id, email], 'verify-email')

    verify_link = url_for('users.verify_token', token=token, _external=True)

    email_body = render_template(
            'users/email_verification.jinja2',
            link=verify_link)

    send_email(email, email_body)


@mod.route('/verify/<token>/')
def verify_token(token):
    """Verify email reset token.

    Loads the user id and the requested email and simultaneously checks
    token age. If not too old, get user with id and set email.
    """
    try:
        user_id, email = ts.loads(token, salt='verify-email', max_age=900)
    except SignatureExpired:
        flash("Sorry, the link has expired. Please try again.", 'error')
        return redirect(url_for('blog.index'))
    except:
        abort(404)

    user = get_object_or_404(User, User.id == user_id)

    user.email = email
    user.save()

    flash("{} is now verified!".format(email), 'success')
    return redirect(url_for('blog.index'))


@mod.route('/reset/', methods=['GET', 'POST'])
def reset():
    """View for requesting password reset.

    If a non-registred email address is entered, do nothing but tell
    user that an email has been sent. This way we do not expose what
    email addresses are registred.

    If a registred email address is entered, get the id of the user the
    email address is registred to and create a timestamped token with
    the id. The token is sent as a part of a link to the email of that
    user.

    The view which the link leads to checks that the token is intact and
    has not been tampered with, checks its age, and checks if the
    password has been changed after the token was created. This means:
    * Tokens are time limited.
    * Multiple tokens can be valid at the same time, which prevents
        confusion for the user.
    * If the password is changed, using a token or in some other way,
        all tokens generated before that change become invalid.
    * Tokens are therefore single use.
    * Tokens are not stored anywhere other than in the email sent to
        user.
    """
    reset_flash = \
        "A password reset link valid for one hour has been sent to {}."

    form = ExistingEmailForm()

    if form.validate_on_submit():
        user = User.get(User.email == form.email.data)
        token = ts.dumps(user.id, salt='recover-key')

        recover_url = url_for('.reset_token', token=token, _external=True)

        email_body = render_template(
            'users/password_reset_email.jinja2',
            name=user.first_name,
            link=recover_url)

        send_email(user.email, email_body)

        flash(reset_flash.format(form.email.data), 'info')
        return redirect(url_for('.login'))

    elif form.email.data:
        flash(reset_flash.format(form.email.data), 'info')
        return redirect(url_for('.login'))

    elif form.errors:
        flash("Please enter your email.", 'error')

    return render_template('users/reset.html', form=form)


@mod.route('/reset/<token>/', methods=['GET', 'POST'])
def reset_token(token):
    """Verify a password reset token.

    Checks if the token is intact and has not been tampered with,
    checks its age, and checks if the password has been changed after
    the token was created.

    If the token is valid, allow user to enter a new password.

    Note: itsdangerous saves the timestamp in tokens in UTC!
    """
    expired = "Sorry, the link has expired. Please try again."
    invalid = "Sorry, the link appears to be broken. Please try again."

    try:
        data, timestamp = ts.loads(token, salt='recover-key', max_age=3600,
                                   return_timestamp=True)
        user = User.get(User.id == data)
    except SignatureExpired:
        flash(expired, 'error')
        return redirect(url_for('.login'))
    except:
        flash(invalid, 'error')
        return redirect(url_for('.login'))

    if timestamp < user._password_timestamp:
        flash(expired, 'error')
        return redirect(url_for('.login'))

    form = PasswordForm()

    if form.validate_on_submit():
        user.password = form.password.data
        user.save()
        flash("Your password has been reset!", 'success')
        return redirect(url_for('.login'))

    return render_template('users/reset_token.html', form=form)