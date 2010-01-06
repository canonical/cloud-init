
import ec2init

class DataSource:
    userdata = None
    metadata = None
    userdata_raw = None

    def __init__(self):
       pass

    def store_user_data_raw(self):
        fp=fopen(user_data_raw,"wb")
        fp.write(self.userdata_raw)
        fp.close()
    
    def store_user_data(self):
        fp=fopen(user_data,"wb")
        fp.write(self.userdata)
        fp.close()

    def get_user_data(self):
        if self.userdata == None:
            self.userdata = ec2init.preprocess_user_data(self.userdata_raw)

        return self.userdata
