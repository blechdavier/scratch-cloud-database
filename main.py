from scratchclient import ScratchSession
from time import sleep, time

def get_packet_chunks_from_file(path):
    try:
        with open("store/{}.txt".format(path), "r") as f:
            data = f.read()
    except FileNotFoundError:
        return ["50"] # Empty
    chunks = []
    while len(data) > 0:
        if len(data) > 255:
            chunks.append("5"+data[:255])
            data = data[255:]
        elif len(data) == 255:
            chunks.append("5"+data[:255])
            data = data[255:]
            chunks.append("5")
        else:
            chunks.append("5"+data)
            data = ""
    return chunks

username = input("Enter your Scratch Username: ")
password = input("Enter your Scratch Password: ")

session = ScratchSession(username, password)

connection = session.create_cloud_connection(764232422)

for i in range(1, 10):
    connection.set_cloud_variable("☁ {}".format(i), "0")
    print("resetting ☁ {}".format(i))

class DataLane:
    def __init__(self, variable_name):
        self.name = ""
        self.data = ""
        self.active = False
        self.variable_name = variable_name
        self.request_type = "none"
        self.ack = False
        self.writing = False
        self.last_updated = time()
    
    def process_get_request_chunk(self, chunk):
        self.writing = False
        self.ack = True
        self.last_updated = time()
        if not self.request_type == "get":
            self.request_type = "get"
            self.name = ""
        self.name += chunk
        if len(chunk) < 255:
            self.ack = False
            self.process_get_request()

    def process_get_request(self):
        print("get request: {}".format(self.name))
        self.data = get_packet_chunks_from_file(self.name)
        self.writing = True

    def process_set_request_name_chunk(self, chunk):
        self.last_updated = time()
        self.writing = False
        self.ack = True
        if not self.request_type == "set":
            self.request_type = "set"
            self.name = ""
            self.data = ""
        self.name += chunk

    def process_set_request_data_chunk(self, chunk):
        self.last_updated = time()
        self.writing = False
        self.ack = True
        self.data += chunk
        if len(chunk) < 255:
            self.process_set_request()
    
    def process_set_request(self):
        print("set request: {} {}".format(self.name, self.data))
        if len(self.name) > 192:
            print("name too long to set")
        else:
            with open("store/{}.txt".format(self.name), "w") as f:
                f.write(self.data)
        self.active = False
        self.request_type = "none"
        connection.set_cloud_variable(self.variable_name, "0")
        print("released channel {}".format(self.variable_name))
    
    def try_send_data(self):
        if self.writing and connection.get_cloud_variable(self.variable_name)[0] in ["2", "7"]:
            if len(self.data) > 0:
                connection.set_cloud_variable(self.variable_name, self.data[0])
                print("sent packet chunk: {}".format(self.data[0]))
                self.last_updated = time()
                self.data = self.data[1:]
            else:
                self.writing = False
                self.active = False
                self.request_type = "none"
                connection.set_cloud_variable(self.variable_name, "0")
                print("released channel {}".format(self.variable_name))
        

    def try_send_ack(self):
        if self.ack:
            connection.set_cloud_variable(self.variable_name, "6")
            self.ack = False

    def try_prune(self):
        if time() - self.last_updated > 5:
            self.active = False
            self.request_type = "none"
            connection.set_cloud_variable(self.variable_name, "0")
            print("released channel {} because of timeout".format(self.variable_name))

    
        

lanes = [DataLane("☁ {}".format(i+1)) for i in range(9)]

@connection.on("set")
def on_set(variable):
    match variable.name:
        case "☁ request_user_queue":
            print("request from user {}".format(variable.value))
            for i in range(9):
                if lanes[i].active == False:
                    # reset data and name of lane and set it to active
                    lanes[i].active = True
                    lanes[i].data = ""
                    lanes[i].name = ""
                    print("assigned channel ☁ {}".format(i+1))
                    connection.set_cloud_variable("☁ {}".format(i+1), "1{}".format(variable.value))
                    lanes[i].last_updated = time()
                    break
        case _:
            valstr = str(variable.value)
            varnum = int(variable.name[2])-1
            match valstr[0]:
                case "2":
                    # C->S client get request chunk (up to 255 digits of data)
                    # if less than 255 digits, then the request is finished
                    lanes[varnum].process_get_request_chunk(valstr[1:])
                case "3":
                    # C->S client set request name chunk (up to 255 digits of data)
                    # after a number of these requests, the name is finished and data is sent
                    lanes[varnum].process_set_request_name_chunk(valstr[1:])
                case "4":
                    # C->S client set request data chunk (up to 255 digits of data)
                    # if less than 255 digits, then the request is finished
                    lanes[varnum].process_set_request_data_chunk(valstr[1:])
                case "7":
                    if len(lanes[varnum].data) > 0:
                        print("acknowledged ☁ {}".format(varnum+1))
                case _:
                    print("Unknown packet type {}".format(valstr[0]))
                    print("data: {}".format(valstr[1:]))

while True:
    for i in range(9):
        if lanes[i].active:
            lanes[i].try_send_ack()
            lanes[i].try_send_data()
            lanes[i].try_prune()
    sleep(0.1)