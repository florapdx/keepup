from flask import render_template, flash, redirect
from keepup import app, db, lm, oid, oauth, twitter
from flask import render_template, flash, redirect, session, url_for, request, g
from flask.ext.login import login_user, logout_user, current_user, login_required
from models import User, Post, FeedUrls, ROLE_USER, ROLE_ADMIN
from datetime import datetime
from forms import LoginForm, EditForm

@app.route('/')
@app.route('/index')
@login_required
def index():
    user = { 'nickname': g.user.nickname } # fake user
    posts = [ # fake array of posts
        {
            'author': { 'nickname': 'John' },
            'body': 'Beautiful day in Portland!'
        },
        {
            'author': { 'nickname': 'Susan' },
            'body': 'The Avengers movie was so cool!'
        }
    ]
    urls = [ # fake array of urls
        {
            'url': 'http://www.chesnok.com',
        },
        {
            'url': 'http://www.chesnok.com',
        }
    ]
    return render_template("index.html",
        title = 'Home',
        user = user,
        posts = posts,
        urls = urls)

@app.route('/login', methods = ['GET', 'POST'])
@oid.loginhandler
def login():
    if g.user is not None and g.user.is_authenticated():
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        session['remember_me'] = form.remember_me.data
        return oid.try_login(form.openid.data, ask_for = ['nickname', 'email'])
    return render_template('login.html',
        title = 'Sign In',
        form = form,
        providers = app.config['OPENID_PROVIDERS'])

@lm.user_loader
def load_user(id):
    return User.query.get(int(id))

@oid.after_login
def after_login(resp):
    if resp.email is None or resp.email == "":
        flash('Invalid login. Please try again.')
        redirect(url_for('login'))
    user = User.query.filter_by(email = resp.email).first()
    if user is None:
        nickname = resp.nickname
        if nickname is None or nickname == "":
            nickname = resp.email.split('@')[0]
        nickname = User.make_unique_nickname(nickname)
        user = User(nickname = nickname, email = resp.email, role = ROLE_USER)
        db.session.add(user)
        db.session.commit()
        app.logger.info('commited %s' % nickname)
    remember_me = False
    if 'remember_me' in session:
        remember_me = session['remember_me']
        session.pop('remember_me', None)
    login_user(user, remember = remember_me)
    return redirect(request.args.get('next') or url_for('index'))

@app.before_request
def before_request():
    g.user = current_user

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/user/<nickname>')
@login_required
def user(nickname):
    user = User.query.filter_by(nickname = nickname).first()
    if user == None:
        flash('User ' + nickname + ' not found.')
        return redirect(url_for('index'))
    posts = [
        { 'author': user, 'body': 'Test post #1' },
        { 'author': user, 'body': 'Test post #2' }
    ]
    return render_template('user.html',
        user = user,
        posts = posts)

@app.before_request
def before_request():
    g.user = current_user
    if g.user.is_authenticated():
        g.user.last_seen = datetime.utcnow()
        db.session.add(g.user)
        db.session.commit()

@app.route('/edit', methods = ['GET', 'POST'])
@login_required
def edit():
    form = EditForm(g.user.nickname)
    if form.validate_on_submit():
        g.user.nickname = form.nickname.data
        g.user.about_me = form.about_me.data
        db.session.add(g.user)
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('edit'))
    else:
        form.nickname.data = g.user.nickname
        form.about_me.data = g.user.about_me
    return render_template('edit.html',
        form = form)

@app.errorhandler(404)
def internal_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@twitter.tokengetter
def get_twitter_token(token=None):
    token = session.get('twitter_token')
    if token:
        return token
    else:
        return

@app.route('/authorize')
@login_required
def authorize():
    return twitter.authorize(callback=url_for('oauth_authorized',
        next=request.args.get('next') or request.referrer or None))

from flask import redirect

@app.route('/oauth-authorized')
@twitter.authorized_handler
@login_required
def oauth_authorized(resp):
    next_url = request.args.get('next') or url_for('index')
    if resp is None:
        return redirect(next_url)

    this_user = User.query.filter_by(twitter_username = resp['screen_name']).first()
    if this_user is None:
        userid = g.user.get_id()
        app.logger.info("Userid: %s" % userid)
        update_account = User.query.filter_by(id = userid)
        app.logger.info("User account: %s" % update_account.nickname)
        update_account.twitter_username = resp['screen_name']
        update_account.token = resp['oauth_token']
        update_account.secret = resp['oauth_token_secret']
        db.session.add(update_account)
        db.session.commit()
        # we don't allow token storage until this auth step
        # so no 'else' needed
    else:
        flash('You must be logged in to authorize Twitter.')

    return redirect(next_url)

