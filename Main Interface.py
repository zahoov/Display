"""
AUTHOR: Xavier Biancardi

        Portions that deal with receiving CAN messages have been adapted from Calvin Lefebvre's code

PURPOSE: This is an app to be used on small 5" touch screen displays inside Hydra's trucks. It is used to display information gathered from the truck monitoring scripts in an easy to read
         touch screen GUI. It (currently) consists of 7 pages: Main Menu, H2 Fuel Gauge, H2 Injection Rate, Tank Pressure and Temperature, Fault Information, Leakage Information, and the Screen Saver.
         The pages' functions/purposes are described below. The app automatically runs on the boot up of the Raspberry Pi computer it is loaded on as long as the appropriate scripts/files are added as described
         in the README. The app requires a few files to run properly, these include the 2 image files "cadran.png" which is the gauge and "needle.png" which is the needle on the gauge. The entire app is built with Kivy
         via Python 3.7 and requires an up to date Python 3.7 as well as Kivy install to work. The file paths are currently set up for the Raspberry Pi computer that the app was built for but can be easily changed to
         fit any computer OS or file path.

Page Descriptions:

         Main Menu: This page is where the app initially loads to and consists of 5 buttons that each take you to the individual information pages. In the top left of the page is an area where in the case of a system fault
         a red message saying "FAULT" as well as the fault number code will be displayed. In the top right of the page is an area where the current mode of the truck (Hydrogen or Diesel) is displayed.

         H2 Fuel Gauge: This is the page that shows the current Hydrogen fuel level in the truck. It displays the percentage as a number in the bottom of the page as well as graphically in the form of the fuel gauge itself.
         In the bottom left of the page is a button that says "BACK" which when pressed takes the user back to the Main Menu page. As with all of the screens/pages the top left displays any faults and the top right displays
         the current engine mode of the truck

         H2 Injection Rate: Very similar in appearance to the H2 Fuel Gauge screen, this page shows the current instantaneous Hydrogen injection rate into the engine. It is displayed graphically as a percentage of the maximum
         injection rate on the gauge as well as the specific value in kg/h in the bottom of the page. This screen includes the same "BACK" button, Fault, and engine mode displays as all the other pages.

         Tank Pressure and Temperature: This page shows the current temperatures of all of the Hydrogen tanks in addition to the readings from the 2 in-line pressure sensors. Includes the same buttons and corner displays as
         the other screens

         Fault Information: This page provides more in depth information about the fault (if any) occurring within the truck. On the left it shows the fault code and on the right has the brief description of what the fault is.
         This is mainly for the driver to be able to inform the technician(s) and thus the fault description is brief and requires knowledge of the fault codes/messages to understand. Has the same "BACK" button and engine mode
         display however does not include a Fault display in the top left as that would be redundant since the page already displays that information

         Leakage Information: This page provides information on the status/severity of any Hydrogen leaks occurring in the truck. Includes the same corner buttons and displays as the other screens.

         Screen Saver: There is no direct button to access this screen. If there is no user interaction on any of the pages for a designated amount of time (controlled by the variable 'delay') then the app will automatically
         change to this page. To avoid burn in the Hydra logo is animated to slowly bounce around

Any reference to the Kivy back end or the Kivy code relates to the code held within the "fuelgauge.kv" file -- it will/needs to be in the same folder as this code for the app to work

"""

import time

import can
from threading import Thread
import os

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.properties import NumericProperty, ListProperty, StringProperty
from kivy.uix.screenmanager import ScreenManager, Screen

# The conversion factor is used to convert the raw numerical data into degrees to move the needle
# default is 1.8 which works for a 0-100 slider, this is because when the needle is pointing straight up (at the 50) it is at 0˚ and since
# the maximum angles for the needle will be 50 points on the dial either way to get this as +/- 90˚ you multiply the value by 1.8.
# To put it more simply 50 * 1.8 = 90, the needle has to be able to rotate 180˚ total and the gauge is from 0-100, 100 * 1.8 = 180
# cf = conversion_factor
cf = 1.8
# The delay is how long the app goes without user input before it changes to the screen saver
delay = 1000

_canIdTank123 = "cff3d17"
_canIdTank456 = "cff4017"
_canIdNira3 = "cff3e17"
_canIdWheelSpeed = "18fef100"


#################################################################################################################

def msg_receiving():
    '''outDir = sys.argv[1]  # "/home/pi/rough/logger-rbp-python-out/lomack150_"
    numCAN = int(sys.argv[2])  # 2
    bRate = int(sys.argv[3])  # 250000 or 500000
    CANtype = sys.argv[4]  # OCAN or ACAN
    numTank = int(sys.argv[5])
    volumeStr = sys.argv[6]'''

    outDir = "Display/out/hydraFL"  # "/home/pi/rough/logger-rbp-python-out/lomack150_"
    numCAN = 1  # 2
    bRate = 500000  # 250000 or 500000
    CANtype = "RBP15"  # OCAN or ACAN
    numTank = 5
    volumeStr = "202,202,202,202,148"

    volumeL = [float(x) for x in volumeStr.split(",")]

    os.system("sudo /sbin/ip link set can0 down")
    if numCAN == 2:
        os.system("sudo /sbin/ip link set can1 down")

    # Make CAN interface to 250 or 500kbps
    setCANbaudRate(numCAN, bRate)

    # Connect to Bus
    bus0 = connectToLogger('can0')
    if numCAN == 2:
        bus1 = connectToLogger('can1')

    # Continually recieved messages
    readwriteMessageThread(bus0, outDir, numCAN, bRate, CANtype, numTank, volumeL)
    # if numCAN == 2:
    #    readwriteMessageThread(bus1, outDir, numCAN, bRate, CANtype + "1", numTank, volumeL)

    # Continually write readMessages
    try:
        while True:
            pass

    except KeyboardInterrupt:
        # Catch keyboard interrupt
        os.system("sudo /sbin/ip link set can0 down")
        if numCAN == 2:
            os.system("sudo /sbin/ip link set can1 down")
        print('\n\rKeyboard interrtupt')


def readwriteMessageThread(bus, outDir, numCAN, bRate, CANv, numTank, volumeL):
    """
    In seperate thread continually recieve messages from CAN logger
    """
    # Start receive thread
    t = Thread(target=can_rx_task, args=(bus, outDir, numCAN, bRate, CANv, numTank, volumeL))
    t.start()


def can_rx_task(bus, outDir, numCAN, bRate, CANv, numTank, volumeL):
    """
    CAN receive thread
    """
    curFname = None
    outF = None
    prevTime = ("-1", "-1", "-1")

    livefeedNiraErrorFname = "_".join([outDir, CANv, "liveUpdate-NiraError.txt"])
    livefeedHmassFname = "_".join([outDir, CANv, "liveUpdate-Hmass.txt"])

    prevNiraError = None

    tempL = []
    maxNumTanks = 6
    for i in range(maxNumTanks): tempL.append(None)
    presT1 = None
    wheelSpeed = None
    railPressure = None

    prevSec = None

    curVarL = [railPressure, presT1, wheelSpeed]

    while True:
        # recieve message and extract info
        (outstr, timeDateV) = createLogLine(bus.recv())

        (ymdFV, hourV, ymdBV, hmsfV) = timeDateV

        prevYmdBV = ymdBV
        prevHmsfV = hmsfV
        prevHour = hourV
        prevTime = (prevYmdBV, prevHmsfV, prevHour)

        (prevNiraError, tempL, curVarL, prevSec) = liveUpdateTruck(outstr, livefeedNiraErrorFname,
                                                                   livefeedHmassFname,
                                                                   prevNiraError, prevTime, tempL,
                                                                   curVarL, volumeL, numTank,
                                                                   maxNumTanks, prevSec)
        # if not(HtotalMass == None):
        #     WRITE CODE HERE ... use HtotalMass


def createLogLine(message):
    """
    Format the CAN message
    """
    # Time Stamp
    (ymdFV, hmsfV, hourV, ymdBV) = extractTimeFromEpoch(message.timestamp)

    # PGN
    pgnV = '0x{:02x}'.format(message.arbitration_id)

    # Hex
    hexV = ''
    for i in range(message.dlc):
        hexV += '{0:x} '.format(message.data[i])

    outstr = " ".join([hmsfV, "Rx", "1", pgnV, "x", str(message.dlc), hexV]) + " "
    timeDateV = (ymdFV, hourV, ymdBV, hmsfV)
    return (outstr, timeDateV)


def extractTimeFromEpoch(timeStamp):
    """
    Extract all the relative time and date info from CAN timestamp
    """
    ymdFV = time.strftime('%Y%m%d', time.localtime(timeStamp))
    ymdBV = time.strftime('%d:%m:%Y', time.localtime(timeStamp))
    hmsV = time.strftime('%H:%M:%S', time.localtime(timeStamp))
    hourV = time.strftime('%H', time.localtime(timeStamp))
    millsecondV = str(timeStamp).split(".")[1][:3]
    return (ymdFV, hmsV + ":" + millsecondV, hourV, ymdBV)


def liveUpdateTruck(outstr, livefeedNiraErrorFname, livefeedHmassFname, prevNiraError, YDM,
                    tempL, curVarL, volumeL, numTank, maxNumTanks, prevSec):
    """
    ...
    """

    app = App.get_running_app()

    splt = outstr.strip().split(" ")

    # Timestamp with date
    monthNumToChar = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
                      9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
    [dayV, monthV, yearV] = YDM[0].split(":")
    hmsStr = ":".join(YDM[1].split(":")[:3])
    outDate = " ".join([dayV, monthNumToChar[int(monthV)], yearV, hmsStr])

    [railPressure, presT1, wheelSpeed] = curVarL
    # date, can ID, hex value
    if (outstr[0] != "*"):
        try:
            dateV = splt[0]
            idV = splt[3].lower()[2:]
            hexVsplt = splt[6:]
            hexV = ""
            for h in hexVsplt:
                if len(h) == 1:
                    hexV += "0" + h
                elif len(h) == 2:
                    hexV += h
        except IndexError:
            hexV = ""
            idV = ""

        if len(hexV) == 16:
            #######################################################################################
            # Nirai7LastFaultNumber_spnPropB_3E
            if (idV == _canIdNira3):
                dateCond0 = (len(splt[0]) != 12)
                dateCond1 = ((len(splt[0]) == 13) and (len(splt[0].split(":")[-1]) == 4))

                piCcond = ((len(hexV) != 16) or (dateCond0 and not (dateCond1)))

                if piCcond:
                    pass
                else:
                    nirai7LastFaultNumber = (enforceMaxV(((int(hexV[6:8], 16))), 255) * 1.0)

                    app.error_code = str(int(nirai7LastFaultNumber))

                    if prevNiraError == None:
                        prevNiraError = nirai7LastFaultNumber
                    elif nirai7LastFaultNumber != prevNiraError:

                        'INSERT CODE HERE'

            #######################################################################################
            # Temperature and Pressure T1-T3
            if (idV == _canIdTank123):
                presT1 = (enforceMaxV(((int(hexV[0:2], 16)) +
                                       ((int(hexV[2:4], 16) & 0b00001111) << 8)), 4015) * 0.1)
                presT2 = (enforceMaxV((((int(hexV[2:4], 16) & 0b11110000) >> 4) +
                                       ((int(hexV[4:6], 16)) << 4)), 4015) * 0.1)
                tempL[0] = (enforceMaxV(((int(hexV[10:12], 16))), 250) * 1.0) - 40.0
                tempL[1] = (enforceMaxV(((int(hexV[12:14], 16))), 250) * 1.0) - 40.0
                tempL[2] = (enforceMaxV(((int(hexV[14:16], 16))), 250) * 1.0) - 40.0

                app.press1 = str(presT1) + ' bar'

                app.temp0 = str(tempL[0]) + '˚C'
                app.temp1 = str(tempL[1]) + '˚C'
                app.temp2 = str(tempL[2]) + '˚C'

            #######################################################################################
            # Temperature and Pressure T4-T6
            elif (idV == _canIdTank456):
                tempL[3] = (enforceMaxV(((int(hexV[10:12], 16))), 250) * 1.0) - 40.0
                tempL[4] = (enforceMaxV(((int(hexV[12:14], 16))), 250) * 1.0) - 40.0
                tempL[5] = (enforceMaxV(((int(hexV[14:16], 16))), 250) * 1.0) - 40.0

                app.temp3 = str(tempL[3]) + '˚C'
                app.temp4 = str(tempL[4]) + '˚C'
                app.temp5 = str(tempL[5]) + '˚C'



            #######################################################################################
            # Rail pressure
            elif (idV == _canIdNira3):
                railPressure = (enforceMaxV(((int(hexV[12:14], 16))), 4015) * 0.1)

                app.press2 = str('%.2f' % railPressure) + ' bar'

            #######################################################################################
            # Wheel-Based Vehicle Speed
            elif (idV == _canIdWheelSpeed):
                wheelSpeed = (enforceMaxV(((int(hexV[2:4], 16)) + ((int(hexV[4:6], 16)) << 8)),
                                          64259) * 0.003906)
            #######################################################################################
            # Hydrogen injection rate
            elif ((idV == "cff3f28") or (idV == "cff3ffa")):
                app.HinjectionV = (enforceMaxV(((int(hexV[12:14], 16)) + ((int(hexV[14:16], 16)) << 8)), 64255) * 0.02)

            #######################################################################################
            # Hydrogen leakage

            elif ((idV == "cff3e28") or (idV == "cff3efa")):
                app.Hleakage = (enforceMaxV(((int(hexV[2:4], 16))), 250) * 0.4)

            #######################################################################################
            # curHr = int(dateV.split(":")[1])
            # if ((curHr in [0, 15, 30, 45]) and (curHr != lastQuarterHour)):
            curSec = int(dateV.split(":")[2])
            if curSec != prevSec:
                ###################################################################################
                # H mass calculation
                HtotalMass = None
                if (not (None in tempL) and (presT1 != None)):
                    HtotalMassL = []
                    for t in range(numTank):
                        # Only consider tank 1 hydrogen pressure
                        currHtotalMassT = hydrogenMassEq2(presT1, tempL[t], volumeL[t])
                        HtotalMassL.append(currHtotalMassT)

                    HtotalMass = round(sum(HtotalMassL), 1)

                    'Insert code here'

                tempL = []
                for i in range(maxNumTanks): tempL.append(None)
                presT1 = None
                railPressure = None
                wheelSpeed = None

                prevSec = curSec
                # lastQuarterHour = curHr

    curVarL = [railPressure, presT1, wheelSpeed]

    return (prevNiraError, tempL, curVarL, prevSec)


def connectToLogger(canV):
    """
    Connect to Bus
    """

    app = App.get_running_app()

    try:
        app.bus = can.interface.Bus(channel=canV, bustype='socketcan_native')
    except OSError:
        print('Cannot find PiCAN board.')
        exit()
    return app.bus


def setCANbaudRate(numCAN, bRate):
    """
    Make CAN interface to 250 or 500 kbps
    """
    os.system("sudo /sbin/ip link set can0 up type can bitrate " + str(bRate))
    if numCAN == 2:
        os.system("sudo /sbin/ip link set can1 up type can bitrate " + str(bRate))
    time.sleep(0.1)


def hydrogenMassEq2(pressureV, tempV, volumeV):
    """
    Calculate the hydrogen mass using more complex equation
    Value returns in unit kilo grams
    """

    app = App.get_running_app()

    var1 = 0.000000001348034
    var2 = 0.000000267013
    var3 = 0.00004247859
    var4 = 0.000001195678
    var5 = 0.0003204561
    var6 = 0.0867471

    component1 = (((-var1 * (tempV ** 2)) + (var2 * tempV) - var3) * (pressureV ** 2))
    component2 = ((var4 * (tempV ** 2)) - (var5 * tempV) + var6) * pressureV

    HmassTotal = (component1 + component2) * volumeV
    HmassTotalKg = HmassTotal / 1000.0

    app.hMass = HmassTotalKg

    print(HmassTotalKg)

    return HmassTotalKg


def enforceMaxV(origV, maxV):
    """
    ...
    """
    if origV < maxV:
        return origV
    else:
        return maxV


#################################################################################################################

# This function checks the value read by modeReader and checks what it is -- if it is 0 or 1 it sets the engine_mode string variable to 'H2\nMODE' which is just H2 MODE on separate lines, otherwise it sets the variable
# to 'DIESEL\nMODE'. It also then changes the color of the text to either green or grey
def truckEngineMode(dt):
    app = App.get_running_app()

    if (app.mode_num == '0') or (app.mode_num == '1'):
        app.engine_mode = 'H2\nMODE'
        app.mode_color = [0, 1, 0, 1]
    else:
        app.engine_mode = 'DIESEL\nMODE'
        app.mode_color = [0.431, 0.431, 0.431, 1]


# This checks what value the error_code variable has and if it has no value or is 255 then since there is no fault the function sets the error_base string variable to ' ' which is just blank
# If error_code is any other number it then changes the error_base variable to a couple different things. This function is called repeatedly every 2s so it checks to see what error_base is currently
# if it is blank it changes it to 'FAULT' if it says 'FAULT' it changes it to the error code, and if it is the error code it changes it to 'FAULT' essentially flipping between displaying 'FAULT' and
# the error code every 2s
def errorMsg(dt):
    app = App.get_running_app()

    if (app.error_code == '255') or (app.error_code == ''):
        app.error_base = ''
    else:
        if app.error_base == '':
            app.error_base = 'FAULT'
        elif app.error_base == 'FAULT':
            app.error_base = '#' + app.error_code
        elif app.error_base == '#' + app.error_code:
            app.error_base = 'FAULT'


# This function just changes the current page to the 'third' which is what the screen saver page is defined as in the Kivy back end
def callback(dt):
    app = App.get_running_app()
    # app.root.current just calls the the Kivy ScreenManger class that handles all of the screens and changes it to the screen defined as 'third'
    app.root.current = 'third'


def message_setup(dt):
    app = App.get_running_app()

    # Creates the CAN message --> arbitration_id = destination address
    try:
        app.toggle_msg = can.Message(arbitration_id=0xCFF41F2, data=app.msg_data)
    except AttributeError:
        bus_status = 0
    else:
        bus_status = 1

    while bus_status == 0:
        try:
            app.toggle_msg = can.Message(arbitration_id=0xCFF41F2, data=app.msg_data)
        except AttributeError:
            bus_status = 0
        else:
            bus_status = 1
        print(bus_status)


    # Sends the CAN message to whatever 'bus' was set to every period in seconds (0.25 = 250ms)
    try:
        app.task = app.bus.send_periodic(app.toggle_msg, 0.25)
        if not isinstance(app.task, can.ModifiableCyclicTaskABC):
            print("This interface doesn't seem to support modification")
            app.task.stop()
            return
    except AttributeError:
        pass




# This is the menu screen that the app defaults to and provides buttons to access all of the information screens
class MainMenu(Screen):

    # When the user enters the page a transition to the screen-saver is scheduled for delay seconds from now
    def on_enter(self):
        Clock.schedule_once(callback, delay)

    # Listens for the touch up on the screen
    def on_touch_up(self, touch):
        # Clock.unschedule(FUNCTION) just cancels whatever scheduling was put onto the designated function. It is used here as the screen saver delay tool. When the user touches the screen the function that changes
        # the screen to the screen saver will be unscheduled and then rescheduled by the Clock call below this, this basically just resets the delay timer on the screen saver
        Clock.unschedule(callback)
        Clock.schedule_once(callback, delay)

    # Unschedules the screensaver when leaving the current screen
    def on_leave(self):
        Clock.unschedule(callback)


# This is the screen saver page -- for its design/visual setup look in the Kivy back end code (in the 'root_widget')
class ScreenSaver(Screen):
    # Sets the speed that the logo will travel at based on the size of the screen
    velocity = ListProperty([Window.width / 200, Window.height / 200])
    screen_pos = ListProperty([0, 0])

    # Updates the position of the Hydra logo (animates it)
    def update(self, dt):
        self.screen_pos[0] += self.velocity[0]
        self.screen_pos[1] += self.velocity[1]
        if self.screen_pos[0] < 0 or self.screen_pos[0] > ((Window.width * 2 / 3)):
            self.velocity[0] *= -1
        # or (self.screen_pos[1] + self.height) > Window.height
        if self.screen_pos[1] < 0 or self.screen_pos[1] > (Window.height * (1 - (1.8 * (2.5 / 12)))):
            self.velocity[1] *= -1

    app = App.get_running_app()

    def on_enter(self):
        Clock.unschedule(callback)
        Clock.schedule_interval(self.update, 1 / 120)

    # Special Kivy function that runs its code when the user touches the screen and releases
    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            # Since this page is the screen saver there is no timer/delay to reset, however when the user touches the screen saver and 'wakes' the device the app will return to the main menu
            self.manager.current = 'menu'

    def on_leave(self):
        Clock.unschedule(self.update)


# This is the fuel gauge screen that displays the current Hydrogen fuel level
class FuelGaugeLayout(Screen):
    # This (dash_val) value is the value that the dashboard/fuel gauge uses and starts at
    dash_val = NumericProperty(0.00)
    dash_label = StringProperty()

    def mass_reader(self, dt):
        app = App.get_running_app()
        # Divides the current hydrogen mass by the maximum possible then multiplies by 100 to get a percentage
        # then assigns this value to the 'dash_val' variable
        self.dash_val = ((app.hMass / 20.7) * 100)

        self.dash_label = '%.2f' % app.hMass

    # Kivy function runs code on entering the page
    def on_enter(self):
        Clock.schedule_once(self.mass_reader)
        Clock.schedule_once(callback, delay)
        Clock.schedule_interval(self.mass_reader, 0.2)

    # Kivy function runs code when the user touches and releases on the screen. This is the delay reset for the screen saver
    def on_touch_up(self, touch):
        Clock.unschedule(callback)
        Clock.schedule_once(callback, delay)

    # Same as in the other classes
    def on_leave(self):
        Clock.unschedule(callback)


# FuelInjectionLayout is the second screen and does what it says on the tin -- it displays the current H2 injection rate
class FuelInjectionLayout(Screen):
    # This variable is what is used to display injection reading at the bottom of the page, is a string property to allow the Kivy back end to read it even when it changes
    hInjection = StringProperty()

    # Same as in the other classes, calls functions as the user enters the page. Upon_entering has the same function as upon_entering_mass and just calls the functions after a 0.5s
    # delay to avoid any issues
    def on_enter(self):
        Clock.schedule_once(self.injection_reader)
        Clock.schedule_interval(self.injection_reader, 0.2)
        # Same as in fuel gauge screen
        Clock.schedule_once(callback, delay)
        # Ticker is what checks to see if the time is at a 15min +1 time interval

    # Kivy function that runs code after the user touches the screen
    def on_touch_up(self, touch):
        Clock.unschedule(callback)
        Clock.schedule_once(callback, delay)

    # This function opens the file that contains the data about the injection rate, reads it and sets it to some variables
    def injection_reader(self, dt):
        app = App.get_running_app()

        # hInj -- This is the variable that contains the injection rate value

        self.hInjection = '%.2f' % app.HinjectionV

    # Same as in the other classes
    def on_leave(self):
        Clock.unschedule(callback)


# This is the page that displays the Fault code and its corresponding message
class ErrorPage(Screen):
    error_expl = StringProperty()

    # Same as in the other classes
    def on_touch_up(self, touch):
        Clock.unschedule(callback)
        Clock.schedule_once(callback, delay)

    # Same as in the other classes, apart from the bottom bit
    def code_checker(self, dt):
        app = App.get_running_app()

        # This part checks to see if the error code is 255 as this means that there is no fault or if the code is greater than 233 as this is out of the possible range of
        # fault codes, if it is 255 it sets the message to 'Everything is running as expected' and if the code is greater than 233 it sets it as 'ERROR: Code outside of range'
        try:
            e_c = int(app.error_code)

        except ValueError:
            print('No NIRA error codes recieved yet')
            return ()

        if e_c == 255:
            self.error_expl = 'Everything is running as expected'
        elif int(app.error_code) >= 233:
            self.error_expl = 'ERROR: Code outside of range'
        else:
            self.error_expl = app.error_list[e_c]
        print(e_c)

    # Same as in the other class
    def on_enter(self):
        Clock.schedule_once(self.code_checker)
        Clock.schedule_interval(self.code_checker, 0.2)
        Clock.schedule_once(callback, delay)

    def on_leave(self):
        Clock.unschedule(self.code_checker)
        Clock.unschedule(callback)


# This is the screen that displays the temperatures and pressures of the tanks and lines from the tanks
class TankTempPress(Screen):

    # Nothing fancy happens on this page, all of the data collection/displaying is handled by the main app class in addition to the kivy code file (fuelgauge.kv)

    def on_enter(self):
        Clock.schedule_once(callback, delay)

    def on_touch_up(self, touch):
        Clock.unschedule(callback)
        Clock.schedule(callback, delay)

    def on_leave(self):
        Clock.unschedule(callback)

    pass


# This is the screen manager that holds all of the other pages together
class MyScreenManager(ScreenManager):
    pass


# Screen that shows the leakage rate
class DynamicLeak(Screen):
    # The numerical value for calculating the needle rotation
    leakAmt = NumericProperty()
    # The value that displays at the bottom of the screen
    leak_display = StringProperty()

    def on_enter(self):
        Clock.schedule_once(self.leakReader, 0)
        Clock.schedule_interval(callback, delay)
        Clock.schedule_interval(self.leakReader, 0.2)

    def on_touch_up(self, touch):
        Clock.unschedule(callback)
        Clock.schedule_once(callback, delay)

    def leakReader(self, dt):
        app = App.get_running_app()

        self.leakAmt = app.Hleakage
        self.leak_display = '%.2f' % app.Hleakage

    def on_leave(self):
        Clock.unschedule(self.leakReader)
        Clock.unschedule(callback)


# This is the lock screen where technicians can lock or unlock the engine mode toggle button -- accessed by hitting the engine mode descriptor
class ModeLocking(Screen):
    # This is the correct password/pin
    password = '1234'

    # This is the descriptor text that says either 'Locked' or 'Unlocked'
    status = StringProperty()

    def on_enter(self):
        # When the user enters the screen checks the current lock status
        Clock.schedule_once(self.launch_status)
        Clock.schedule_once(callback, delay)

    def on_touch_up(self, touch):
        Clock.unschedule(callback)
        Clock.schedule_once(callback, delay)

    def on_leave(self):
        Clock.unschedule(callback)

    # Checks the current lock status and sets the descriptor text accordingly
    def launch_status(self, dt):
        app = App.get_running_app()

        if app.lock_status == '0':
            self.status = 'Unlocked'
        else:
            self.status = 'Locked'

    # Sets the default color of the submit button
    wrong_password_ind = ListProperty([0, 0, 0.8, 1])

    # Called when the user submits their password
    def code_tester(self, text):

        # Allows this function to reference variables/functions from the main app class
        app = App.get_running_app()

        # Checks if the entered password matches the correct one
        if text == self.password:

            # Changes the color of the submit button to Green in order to show the correct password was entered
            self.wrong_password_ind = [0, 1, 0, 1]

            # Checks the current lock status
            if app.lock_status == '1':
                # Toggles the lock status to unlocked
                app.lock_status = '0'
                self.status = 'Unlocked'
            else:
                # Toggles the lock status to locked
                app.lock_status = '1'
                self.status = 'Locked'

            # Writes the current lock status to lock_file.txt to save it across sessions
            fin = open("lock_file.txt", "wt")
            fin.write(app.lock_status)
            fin.close()

        else:
            # Changes the color of the submit button to Red in order to show an incorrect password was entered
            self.wrong_password_ind = [1, 0, 0, 1]


# The main app class that everything runs off of
class FuelGaugeApp(App):
    # The error_code_list is the list of all the errors' number codes
    error_code_list = []
    # The error_list is the list of all the error messages
    error_list = []
    # Just initializing the engine mode variable
    mode_num = str

    # Opens the NIRA error code file and saves th error codes to error_code_list
    with open('Display/2018.08.13 - NIRA J1979 Fault Messages.txt',
              'r') as f:
        lines = f.readlines()
        # Goes line by line and adds the error codes to the 'error_code_list' list
        for l in lines:
            error_code_list.append(l.split(',')[0])
        f.close()

    # Opens the NIRA error code file and saves the fault code descriptions to error_list
    with open('Display/2018.08.13 - NIRA J1979 Fault Messages.txt',
              'r') as f:
        lines = f.readlines()
        # Goes line by line and adds the error messages to the 'error_list' list
        for l in lines:
            error_list.append(l.split(',')[2])
        f.close()

    # lock_file.txt and fuel_file.txt contains and holds the lock and engine mode statuses so they are saved after the screen is turned off
    # Tries to open the file -- if it isn't there it creates it with a default value
    if os.path.isfile("Display/lock_file.txt"):
        fin = open("Display/lock_file.txt", "rt")
        lock_status = fin.read()
        fin.close()
    else:
        fin = open("Display/lock_file.txt", "w")
        fin.write('0')
        lock_status = '0'
        fin.close()

    if os.path.isfile("Display/fuel_file.txt"):
        fin = open("Display/fuel_file.txt", "rt")
        mode_num = fin.read()
        fin.close()
    else:
        fin = open("Display/fuel_file.txt", "w")
        fin.write('2')
        mode_num = '2'
        fin.close()

    if mode_num == '2':
        msg_data = [1]
    else:
        msg_data = [0]

    try:
        bus = can.interface.Bus(channel='can0', bustype='socketcan_native')
    except OSError:
        print('Cannot find PiCAN board.')
        pass


    # These are all of the data values received and decoded by Calvin's code
    temp0 = StringProperty()
    temp1 = StringProperty()
    temp2 = StringProperty()
    temp3 = StringProperty()
    temp4 = StringProperty()
    temp5 = StringProperty()
    press1 = StringProperty()
    press2 = StringProperty()
    Hleakage = NumericProperty()
    HinjectionV = NumericProperty()
    # The 0 inside the brackets is providing an initial value for hMass -- required or else something breaks
    hMass = NumericProperty(0)

    # error_code is a string variable that is used to temporarily store the current error code taken from the text document it is stored in. It is a string because after coming from the .txt the data is a string and
    # must be converted into a float or int to be used as a number
    error_code = StringProperty()

    # error_base is the text that is displayed in the top left hand of most screens -- if there is a fault this variable becomes "FAULT" and then the error code and flips between them
    # It is a StringProperty() which is a Kivy variable type the essentially tells the Kivy back end code to keep checking what its value is/if it changes
    error_base = StringProperty()

    # Similar to error_base this is a string property and will contain the text to be displayed in the top right of most screens. This text tells the user if the truck is in H2 mode or Diesel mode
    engine_mode = StringProperty()

    # In kivy colors are lists (rgba) and to send a color from the python code to the Kivy back end it must be a list property so that Kivy understands what it is receiving. This is needed since when the truck
    # is in H2 mode the text saying this is Green, whereas if the truck is in Diesel mode the text saying that is in Grey
    mode_color = ListProperty()

    # Grabs the global variable and stores it as a local one that the Kivy back end can read
    # The conversion factor is for changing the discrete data values into a specific angle of rotation for the gauges
    conversion_factor = cf

    toggle_msg = can.Message()
    msg_data = []

    # This calls errorMsg every 2 seconds to constantly change the error notification text from "FAULT" to the error code, or if there is no error it sets the text to blank
    Clock.schedule_interval(errorMsg, 2)

    Clock.schedule_once(message_setup)

    # This checks the value of the engine mode number every 2 seconds and changes the notification text if needed
    Clock.schedule_interval(truckEngineMode, 2)
    # Starts Calvin's CAN message reading code in another thread so that it is constantly reading while the display is active
    a = Thread(target=msg_receiving)
    a.start()

    if (mode_num == '0') or (mode_num == '1'):
        engine_mode = 'H2\nMODE'
        mode_color = [0, 1, 0, 1]
    else:
        engine_mode = 'DIESEL\nMODE'
        mode_color = [0.431, 0.431, 0.431, 1]

    # Runs the screen manager that sets everything in motion
    def build(self):
        return MyScreenManager()

    # Called when the user hits the 'Truck Engine Mode' button
    def ModeSender(self):

        # If the display is unlocked (lock_status == '0') it checks to see what the current engine mode is
        if self.lock_status == '0':

            # Depending on the current mode the CAN msg data is set to either 1 or 0 (for H2 mode and Diesel mode respectively)
            if self.mode_num == '2':

                self.msg_data = [1]
                # Then it changes what the current mode number is (ie. it toggles the engine mode for the next time the button is pressed)
                self.mode_num = '0'

            else:
                self.msg_data = [0]
                self.mode_num = '2'

            try:
                self.task.modify_data(self.toggle_msg)
            except AttributeError:
                return
            else:
                # Writing the current engine mode to a text file so that it is saved when the display is shut off
                fin = open("fuel_file.txt", "wt")
                fin.write(self.mode_num)
                fin.close()
                self.toggle_msg = can.Message(arbitration_id=0xCFF41F2, data=self.msg_data)


    # This is for uploading the truck live feed to a wordpress site -- leaving here just in case its needed again
    '''def content_former(self, data):
        i = 0
        vals = []
        formed_content = ''
        data_titles = ['Date: ', 'H2 Mass: ', 'RPM: ', 'H2 Rail Pressure:', 'Tank Pressure:', 'Tank 1 Temp: ',
                       'Tank 2 Temp: ', 'Tank 3 Temp: ', 'Tank 4 Temp: ', 'Tank 5 Temp: ']

        while i < 10:
            vals.append(str(data_titles[i]) + ' ' + str(data[i]) + '\n')
            formed_content = formed_content + str(vals[i])
            i = i + 1

        print(formed_content)

        return formed_content'''


# Makes everything start
if __name__ == '__main__':
    # Tells KIVY to open in fullscreen mode
    Config.set('graphics', 'fullscreen', '0')
    # Tells KIVY what keyboard to use (systemanddock is both physical and onscreen keyboards)
    Config.set('kivy', 'keyboard_mode', 'systemanddock')
    # Tells KIVY to use the custom keyboard layout named pinpad.json and located in the kivy data files
    Config.set('kivy', 'keyboard_layout', 'pinpad')
    # Actually sends all of the previously set config options to the KIVY config controller
    Config.write()
    # Runs the app class that controls the screen
    FuelGaugeApp().run()
