
import can
from can import Message

def main():


    bus = can.interface.Bus(bustype='socketcan', channel='vcan0', bitrate=500000)

    message = Message(data=[1, 2, 3, 4, 5])



    bus.send(message, timeout=0.2)









if __name__ == '__main__':
    main()


