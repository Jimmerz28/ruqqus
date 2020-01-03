from os import environ
import secrets
from flask import *
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from time import sleep

from flaskext.markdown import Markdown
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import *
import threading
import requests

from werkzeug.contrib.fixers import ProxyFix

_version = "0.5.0"

app = Flask(__name__,
            template_folder='./templates',
            static_folder='./static'
           )
app.wsgi_app = ProxyFix(app.wsgi_app, num_proxies=2)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = environ.get("DATABASE_URL")
app.config['SECRET_KEY']=environ.get('MASTER_KEY')
app.config["SERVER_NAME"]=environ.get("domain", None)
app.config["VERSION"]="0.1.0"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config["UserAgent"]="Ruqqus webserver ruqqus.com"

if "localhost" in app.config["SERVER_NAME"]:
    app.config["CACHE_TYPE"]="null"
else:
    app.config["CACHE_TYPE"]="redis"
    
app.config["CACHE_REDIS_URL"]=environ.get("REDIS_URL")
app.config["CACHE_DEFAULT_TIMEOUT"]=60

Markdown(app)
cache=Cache(app)

limit_url=environ.get("HEROKU_REDIS_PURPLE_URL", environ.get("HEROKU_REDIS_ORANGE_URL"))

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=environ.get("HEROKU_REDIS_PURPLE_URL"),
    headers_enabled=True,
    strategy="fixed-window-elastic-expiry"
)

#setup db
_engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
db = sessionmaker(bind=_engine)()
Base = declarative_base()

#import and bind all routing functions
import ruqqus.classes
from ruqqus.routes import *
import ruqqus.helpers.jinja2



#enforce https
@app.before_request
def before_request():
    
    #check ip ban
    if db.query(ruqqus.classes.IP).filter_by(addr=request.remote_addr).first():
        abort(403)

    #check useragent ban
    if db.query(ruqqus.classes.Agent).filter(ruqqus.classes.Agent.kwd.in_(request.headers.get('User-Agent','No Agent').split())).first():
        abort(403)
        
    if request.url.startswith('http://') and "localhost" not in app.config["SERVER_NAME"]:
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

    if not session.get("session_id"):
        session["session_id"]=secrets.token_hex(16)



    db.rollback()

def log_event(name, link):

    sleep(5)

    x=requests.get(link)

    if x.status_code != 200:
        return


    text=f'> **{name}**\r> {link}'



    url=os.environ.get("DISCORD_WEBHOOK")
    headers={"Content-Type":"application/json"}
    data={"username":"ruqqus",
          "content": text
          }

    x=requests.post(url, headers=headers, json=data)
    print(x.status_code)
    

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Headers', "Origin, X-Requested-With, Content-Type, Accept, x-auth"
                         )

    #signups - hit discord webhook
    if request.method=="POST" and response.status_code in [301, 302] and request.path=="/signup":
        link=f'https://{app.config["SERVER_NAME"]}/@{request.form.get("username")}'
        thread=threading.Thread(target=lambda:log_event(name="Account Signup", link=link))
        thread.start()
            
    return response


#start the badge monitoring thread

def badge_monitor():

    while True:

        print("starting badge check thread")

        badge_types=[x for x in db.query(BadgeDef).filter(BadgeDef.qualification_expr.isnot(None)).all()]

        for user in db.query(User).filter_by(is_banned=0).all():

            for badge in badge_types:
                
                if eval(badge.qualification_expr, {}, {'v':user}):
                    
                    if not user.has_badge(badge.id):
                        new_badge=Badge(user_id=user.id,
                                        badge_id=badge.id,
                                        created_utc=int(time.time())
                                        )
                        db.add(new_badge)
                        db.commit()
                        print(f"added {badge.name} to @{user.username}")
                else:
                    bad_badge=user.has_badge(badge.id)
                    if bad_badge:
                        db.delete(bad_badge)
                        db.commit()
                        print(f"removed {badge.name} from @{user.username}")

        print("thread sleeping 1hr")
        time.sleep(3600)

badge_thread=threading.Thread(target=badge_monitor)
badge_thread.start()
    
