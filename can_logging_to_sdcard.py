#!/usr/bin/python3

# Hydra Energy
# 05/24/2019

import can
import time
import os
import queue
import sys
from threading import Thread
import zipfile

_canIdTank123 = "cff3d17"
_canIdTank456 = "cff4017"
_canIdNira3 = "cff3e17"
_canIdWheelSpeed = "18fef100"


def enforceMaxV(origV, maxV):
    """
    ...
    """
    if origV < maxV:
        return origV
    else:
        return maxV


def hydrogenMassEq2(pressureV, tempV, volumeV):
    """
    Calculate the hydrogen mass using more complex equation
    Value returns in unit kilo grams
    """

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
    return HmassTotalKg


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


def setCANbaudRate(numCAN, bRate):
    """
    Make CAN interface to 250 or 500 kbps
    """
    os.system("sudo /sbin/ip link set can0 up type can bitrate " + str(bRate))
    if numCAN == 2:
        os.system("sudo /sbin/ip link set can1 up type can bitrate " + str(bRate))
    time.sleep(0.1)


def connectToLogger(canV):
    """
    Connect to Bus
    """
    try:
        bus = can.interface.Bus(channel=canV, bustype='socketcan_native')
    except OSError:
        print('Cannot find PiCAN board.')
        exit()
    return bus


def topOfFile(ymdBV, hmsfV, bRate):
    """
    Top of log file message
    """
    loggerVersion = "1.1.1"
    topLineL = ["***RPIMASTER Ver " + loggerVersion + "***",
                "***PROTOCOL CAN***",
                "***NOTE: PLEASE DO NOT EDIT THIS DOCUMENT***",
                "***[START LOGGING SESSION]***",
                "***START DATE AND TIME " + ymdBV + " " + hmsfV + "***",
                "***HEX***",
                "***SYSTEM MODE***",
                "***START CHANNEL BAUD RATE***",
                "***CHANNEL 1 - Kvaser - Kvaser Leaf Light v2 #0 (Channel 0), Serial Number- 0, Firmware- 0x000000ef 0x00040003 - " + str(
                    bRate) + " bps***",
                "***END CHANNEL BAUD RATE***",
                "***START DATABASE FILES***",
                "***END DATABASE FILES***",
                "***<Time><Tx/Rx><Channel><CAN ID><Type><DLC><DataBytes>***"]
    return "\n".join(topLineL) + "\n"


def bottomOfFile(prevYmdBV, prevHmsfV):
    """
    Bottom of the file
    """
    bottomLineL = ["***END DATE AND TIME " + prevYmdBV + " " + prevHmsfV + "***",
                   "***[STOP LOGGING SESSION]***"]
    return "\n".join(bottomLineL) + "\n"


def liveUpdateTruck(outstr, livefeedNiraErrorFname, livefeedHmassFname, prevNiraError, YDM,
                    tempL, curVarL, volumeL, numTank, maxNumTanks, prevSec):
    """
    ...
    """
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

                    if prevNiraError == None:
                        prevNiraError = nirai7LastFaultNumber
                    elif nirai7LastFaultNumber != prevNiraError:
                        if os.path.isfile(livefeedNiraErrorFname):
                            livefeedNiraErrorF = open(livefeedNiraErrorFname, "a")
                        else:
                            livefeedNiraErrorF = open(livefeedNiraErrorFname, "w")
                        livefeedNiraErrorF.writelines("\t".join(["-".join(YDM), dateV,
                                                                 str(nirai7LastFaultNumber)]) +
                                                      "\n")
                        prevNiraError = nirai7LastFaultNumber
                        livefeedNiraErrorF.close()

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

            #######################################################################################
            # Temperature and Pressure T4-T6
            elif (idV == _canIdTank456):
                tempL[3] = (enforceMaxV(((int(hexV[10:12], 16))), 250) * 1.0) - 40.0
                tempL[4] = (enforceMaxV(((int(hexV[12:14], 16))), 250) * 1.0) - 40.0
                tempL[5] = (enforceMaxV(((int(hexV[14:16], 16))), 250) * 1.0) - 40.0

            #######################################################################################
            # Rail pressure
            elif (idV == _canIdNira3):
                railPressure = (enforceMaxV(((int(hexV[12:14], 16))), 4015) * 0.1)

            #######################################################################################
            # Wheel-Based Vehicle Speed
            elif (idV == _canIdWheelSpeed):
                wheelSpeed = (enforceMaxV(((int(hexV[2:4], 16)) + ((int(hexV[4:6], 16)) << 8)),
                                          64259) * 0.003906)

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

                ###################################################################################
                if os.path.isfile(livefeedHmassFname):
                    livefeedHmassF = open(livefeedHmassFname, "a")
                else:
                    livefeedHmassF = open(livefeedHmassFname, "w")
                    livefeedHmassF.writelines("\t".join(["date", "H2mass", "RPM",
                                                         "H2RailPressure", "TankPressure"] +
                                                        [("Tank" + str(x + 1) + "Temp") for x in
                                                         range(numTank)]) + "\n")

                if (not (None in tempL[:numTank - 1]) and (wheelSpeed != None) and
                        (railPressure != None) and (presT1 != None)):
                    livefeedHmassF.writelines("\t".join([outDate,
                                                         str(HtotalMass), str(wheelSpeed),
                                                         str(railPressure), str(round(presT1, 1))] +
                                                        [str(x) for x in tempL[:numTank]]) + "\n")

                livefeedHmassF.close()
                tempL = []
                for i in range(maxNumTanks): tempL.append(None)
                presT1 = None
                railPressure = None
                wheelSpeed = None

                prevSec = curSec
                # lastQuarterHour = curHr

    curVarL = [railPressure, presT1, wheelSpeed]

    return (prevNiraError, tempL, curVarL, prevSec)


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

        (outF, prevTime, curFname) = writeToFile(outstr, timeDateV, outF, outDir, prevTime, CANv,
                                                 bRate, curFname)

        (prevNiraError, tempL, curVarL, prevSec) = liveUpdateTruck(outstr, livefeedNiraErrorFname,
                                                                   livefeedHmassFname,
                                                                   prevNiraError, prevTime, tempL,
                                                                   curVarL, volumeL, numTank,
                                                                   maxNumTanks, prevSec)
        # if not(HtotalMass == None):
        #     WRITE CODE HERE ... use HtotalMass


def readwriteMessageThread(bus, outDir, numCAN, bRate, CANv, numTank, volumeL):
    """
    In seperate thread continually recieve messages from CAN logger
    """
    # Start receive thread
    t = Thread(target=can_rx_task, args=(bus, outDir, numCAN, bRate, CANv, numTank, volumeL))
    t.start()


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


def zipLogF(curFname):
    """
    Write current File to zip
    """
    zf = zipfile.ZipFile(curFname + ".zip", mode='w')
    zf.write(curFname + ".log")
    zf.close()


def writeToFile(outstr, timeDateV, outF, outDir, prevTime, CANv, bRate, curFname):
    """
    Write formated CAN message to log file
    Make sure a new log file is created on the hour
    """
    (prevYmdBV, prevHmsfV, prevHour) = prevTime
    (ymdFV, hourV, ymdBV, hmsfV) = timeDateV

    # If new hour then create a new file
    if (prevHour == hourV):
        outF.writelines(outstr + "\n")
    else:
        if (prevHour != "-1"):
            outF.writelines(bottomOfFile(prevYmdBV, prevHmsfV))
            outF.close()
            # zipLogF(curFname) # zip
        curFname = outDir + ymdFV + hourV + "_" + CANv

        if os.path.isfile(curFname + ".log"):
            outF = open(curFname + ".log", "a")
        else:
            outF = open(curFname + ".log", "w")
            outF.writelines(topOfFile(ymdBV, hmsfV, bRate))

    prevYmdBV = ymdBV
    prevHmsfV = hmsfV
    prevHour = hourV
    prevTime = (prevYmdBV, prevHmsfV, prevHour)

    return (outF, prevTime, curFname)


def main():
    outDir = sys.argv[1]  # "/home/pi/rough/logger-rbp-python-out/lomack150_"
    numCAN = int(sys.argv[2])  # 2
    bRate = int(sys.argv[3])  # 250000 or 500000
    CANtype = sys.argv[4]  # OCAN or ACAN
    numTank = int(sys.argv[5])
    volumeStr = sys.argv[6]

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


if __name__ == "__main__":
    main()
