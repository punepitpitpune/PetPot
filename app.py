from crypt import methods
from smtplib import SMTPDataError
from flask import Flask, render_template, request, Response, url_for
from flask_sqlalchemy import SQLAlchemy
import RPi.GPIO as gpio
from datetime import datetime, date, timedelta
import time
import cv2
import threading
from imutils.video import VideoStream
import numpy as np
from picamera.array import PiRGBArray
from picamera import PiCamera

gpio.setmode(gpio.BCM)

blue_ir_storage_pin = 27
blue_ir_bowl_pin = 17
pink_ir_storage_pin = 24
pink_ir_bowl_pin = 23
gpio.setup(blue_ir_storage_pin, gpio.IN)
gpio.setup(blue_ir_bowl_pin, gpio.IN)
gpio.setup(pink_ir_storage_pin, gpio.IN)
gpio.setup(pink_ir_bowl_pin, gpio.IN)

blue_feed_servo_pin = 22
pink_feed_servo_pin = 18

gpio.setwarnings(False)

app = Flask(__name__)

# Config DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:62011212@localhost:3306/petbowlDB'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

now = datetime.now()
current_time = now.strftime("%H:%M:%S")

@app.route('/')
@app.route('/home')
def hello():
   return render_template('index.html')

@app.route('/feature')
def feature():
    return render_template('feature.html')


#------------------------------------------------------------------------------ PiCAM ------------------------------------------------------------------------------#

@app.route("/camera")    
def camera():
    return render_template("camera.html")

@app.route('/picam')
def picam():
    return Response(video_cam(), mimetype='multipart/x-mixed-replace; boundary=frame')

# @app.route("/video_cam")    
def video_cam():
    camera = cv2.VideoCapture(0)
    while True:
        success, frame = camera.read()  # read the camera frame
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    
#------------------------------------------------------------------------------ IR ------------------------------------------------------------------------------#

@app.route("/ir")
def ir():
    return render_template('select_ir_bowl.html')


@app.route("/ir_status", methods=["POST", "GET"])
def ir_status():
    bID = request.form['bowlID']
#     print(bID)
    
    if bID == "1":
        ir_storage_pin = blue_ir_storage_pin
        ir_bowl_pin = blue_ir_bowl_pin
    else:
        ir_storage_pin = pink_ir_storage_pin
        ir_bowl_pin = pink_ir_bowl_pin
    
    gpio.setup(ir_storage_pin, gpio.IN)
    gpio.setup(ir_bowl_pin, gpio.IN)

    if gpio.input(ir_storage_pin)==1:
        storage_status = "Storage is empty, Time to refill!"
    else:
        storage_status = "Storage is not empty, You are good to go!"

    if gpio.input(ir_bowl_pin)==1: 
        bowl_status = "Bowl is empty, your pet finished the food!"
    else:
        bowl_status = "Bowl is not empty, your pet haven't finished the food yet!"


    templateData = {
      'storage_status'  : storage_status,
      'bowl_status': bowl_status,
      }

      
    return render_template('ir.html', **templateData)


#------------------------------------------------------------------------------ FEED ------------------------------------------------------------------------------#

# 11-bluelid 12-bluestorage 21-pinklid 22-pinkstorage
class ServoRecord(db.Model):
    servoRecordID = db.Column(db.Integer, primary_key=True)
    servoID = db.Column(db.Integer)
    servoDate = db.Column(db.String(25))
    servoTime = db.Column(db.String(25))

    def __init__(self, servoID, servoDate, servoTime):
        self.servoID = servoID
        self.servoDate = servoDate
        self.servoTime = servoTime


def turn_servo(servo_pin):
    gpio.setup(servo_pin,gpio.OUT)
    servo = gpio.PWM(servo_pin,50) #blue_feed_servo_pin is pin, 50 = 50Hz pulse

    servo.start(10)
    time.sleep(1)
    #Duty values from 2 to 12 (0 to 180 degrees)
    #Turn to 90 degrees
    servo.ChangeDutyCycle(7)
    time.sleep(1)
    #Turn back to O degrees
    servo .ChangeDutyCycle (2)
    time.sleep(1)

    servo.stop()

    if servo_pin == blue_feed_servo_pin:
        serID = 12
    else:
        serID = 22

    now = datetime.now()
    currentDate = now.strftime("%m/%d/%Y")
    currentTime = now.strftime("%H:%M:%S")

    servosta = ServoRecord(serID, currentDate, currentTime)
    db.session.add(servosta)
    db.session.commit()
    # print('doneeeeeeeeeee')

    return



@app.route("/feed")
def feed():
    return render_template('select_feed_bowl.html')

@app.route("/feed_success", methods=["POST", "GET"])
def feed_success():
    bID = request.form['bowlID']
#     print(bID)
    
    if bID == "1":
        turn_servo(blue_feed_servo_pin)
    else:
        turn_servo(pink_feed_servo_pin)
        
    return render_template('feed_success.html')


#------------------------------------------------------------------------------ SCHEDULE FEED ------------------------------------------------------------------------------#


class personalize_time(db.Model):
    recordID = db.Column(db.Integer, primary_key=True)
    bowlID = db.Column(db.Integer)
    type = db.Column(db.String(25))
    feedTime = db.Column(db.String(25))
    feedDateS = db.Column(db.String(25))
    feedDateE = db.Column(db.String(25))

    def __init__(self, bowlID, type,feedTime, feedDateS, feedDateE):
        self.bowlID = bowlID
        self.type = type
        self.feedTime = feedTime
        self.feedDateS = feedDateS
        self.feedDateE = feedDateE

@app.route("/plan")
def plan():
    return render_template('plan.html')

def addTimeToList(time_list, new_time):
    time_list.append(new_time)
    return time_list

@app.route("/set_success", methods=["POST", "GET"])
def set_success():

    bID = request.form['bowlID']
    tfeed = request.form["time_to_feed"]

    timeInDB = personalize_time.query.filter_by(bowlID=bID, feedTime=tfeed).first()
    if timeInDB:
        return render_template('set_time_fail.html')
    else: 
        feedTime = personalize_time(bID, 1, tfeed, None, None)
        # add to database
        db.session.add(feedTime)
        db.session.commit()
        
        if bID == "1":
            addTimeToList(blue_time, tfeed)
        else:
            addTimeToList(pink_time, tfeed)
    
        print(blue_time)
        print(pink_time)

    return render_template('set_time_success.html')

@app.route("/spe_success", methods=["POST", "GET"])
def spe_success():
    bID = request.form.get('bID')
    sdate = request.form.get('start_date')
    # sdate = datetime.strptime( request.form.get('start_date'),'%d-%m-%Y')
    edate = request.form.get('end_date')
    # edate = datetime.strptime( request.form.get('end_date'),'%d-%m-%Y')
    tfeed = request.form.get("spe_date_time")

    # print(bID)
    # print(type(sdate))
    # print(type(edate))
    # print(tfeed)
    timeInDB = personalize_time.query.filter_by(bowlID=bID, feedTime=tfeed, feedDateS=sdate, feedDateE=edate).first()
    timeInDB = personalize_time.query.filter_by(bowlID=bID, feedTime=tfeed).first()
    if timeInDB:
        return render_template('set_time_fail.html')
    else: 
        feedTime = personalize_time(bID, 0, tfeed, sdate, edate)
        # add to database
        db.session.add(feedTime)
        db.session.commit()
    return render_template('set_time_success.html')


#------------------------------------------------------------------------------ HISTORY ------------------------------------------------------------------------------#
# 11-bluebowl 12-bluestorage 21-pinkbowl 22-pinkstorage
class IRRecord(db.Model):
    irRecordId = db.Column(db.Integer, primary_key=True)
    irSensorId = db.Column(db.Integer)
    irDate = db.Column(db.String(25))
    irTime = db.Column(db.String(25))

    def __init__(self, irSensorId, irDate, irTime):
        self.irSensorId = irSensorId
        self.irDate = irDate
        self.irTime = irTime

@app.route("/select_history")
def select_history():
    return render_template('select_history.html')

@app.route("/servo_history")
def servo_history():

    servoRecordFromDB = ServoRecord.query.all()

    templateData = {
      'irRecordFromDB'  : servoRecordFromDB,
      }
    return render_template('servo_history.html', **templateData, rows=servoRecordFromDB)

@app.route("/ir_history")
def ir_history():

    irRecordFromDB = IRRecord.query.all()

    templateData = {
      'irRecordFromDB'  : irRecordFromDB,
      }
    return render_template('ir_history.html', **templateData)


#------------------------------------------------------------------------------ END ------------------------------------------------------------------------------#

# query feedtime from database
timesFromDB = personalize_time.query.all()

blue_time = []
pink_time = []

for i in timesFromDB:
    if i.bowlID == 1:
        blue_time.append(i.feedTime)
    else:
        pink_time.append(i.feedTime)

print(blue_time)
print(pink_time)

@app.before_first_request
def activate_job():
    def run_job_blue():
        while True:
            now = datetime.now()
            current_time = now.strftime("%H:%M:%S")
            # print(current_time)

            if current_time in blue_time:
                turn_servo(blue_feed_servo_pin)
                
            time.sleep(1)
            
    def run_job_pink():
        while True:
            now = datetime.now()
            current_time = now.strftime("%H:%M:%S")
            
            if current_time in pink_time:
                turn_servo(pink_feed_servo_pin)
                
            time.sleep(1)
          
    def job_check_ir():

        while True:

            now = datetime.now()
            currentDate = now.strftime("%m/%d/%Y")
            currentTime = now.strftime("%H:%M:%S")

            if gpio.input(blue_ir_bowl_pin)==0 or gpio.input(blue_ir_storage_pin)==0 or gpio.input(pink_ir_bowl_pin)==0 or gpio.input(pink_ir_storage_pin)==0:
                
                if gpio.input(blue_ir_bowl_pin)==0:
                    irsta = IRRecord(11, currentDate, currentTime)
                    db.session.add(irsta)
                    db.session.commit()
                    # print('done11')

                if gpio.input(blue_ir_storage_pin)==0:
                    irsta = IRRecord(12, currentDate, currentTime)
                    db.session.add(irsta)
                    db.session.commit()
                    # print('done12')

                if gpio.input(pink_ir_bowl_pin)==0:
                    irsta = IRRecord(21, currentDate, currentTime)
                    db.session.add(irsta)
                    db.session.commit()
                    # print('done21')

                if gpio.input(pink_ir_storage_pin)==0:
                    irsta = IRRecord(22, currentDate, currentTime)
                    db.session.add(irsta)
                    db.session.commit()
                    # print('done22')

                time.sleep(1)
                    
    blue_thread = threading.Thread(target=run_job_blue)
    blue_thread.start()
    
    pink_thread = threading.Thread(target=run_job_pink)
    pink_thread.start()
    
    ir_thread = threading.Thread(target=job_check_ir)
    ir_thread.start()

if __name__ == "__main__":
    db.create_all()
    app.run(host="0.0.0.0", debug=True)
