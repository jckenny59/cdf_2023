
import firebase_admin
from firebase_admin import db
import json

config = {
  "type": "service_account",
  "project_id": "cdf-2023",
  "private_key_id": "44b2bbe229c8b8dcd5de9be910f622e730537c4a",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQClMvEe61NPD1T9\nvblYP0LjAR3K1QrtH5LCrphn9H0TIvfWm6CVD0jgZzDRw1lxRl8gSsKfrRavnKN7\nrmz8211IBm9ti0tetefsiigj8OPitEpVDWhAcJyDV1LA3ZvqD6AeLg5TClZkai1Q\nPK5F0C41pCxNU2C0JvNDuef/D+FW+BBCneAWBA3CmQcGpDGmTWShY3ryJP6Q6tMT\nI6E6l+ndFVHMIcVjiKKipsdhhguFe+0b6H9hJtIUz4NjC7FW2N/vAAFjMs3pq5sb\nJENkJt+rZl/7tpz+OVGF5ZTlyatLyg9kh65xsit/kFqBt7FFDNkyXC8jDQPcaUJ+\nN0MfcbRNAgMBAAECggEAIn88TdYba/+KIoCbczumpovFomURpom41nGqPs8VzUi4\nk3alNmteLwotbihKhbaJx88EzF5TRfHCS+IVPUo7tP4vB6OWZh07ZLBHCJZVqDI4\n8YDeu9IoRN8X11GPrPV9XMAGWr3mY4qukrpRNB/wfmAdpjoakBQwKXzpXuB8kHHf\nWitUxaLCd0Ogi60mdTrSLlbdWu0reV5TPJme1eWFhBwTto9bHZRO/ixWcfIhCLVH\nYQ03PQ/gWmGnICC0POZ0lxbu6cBESPDIynd1Do76O2+/OVhhc3xrGV8YLa5TQhZ/\nJ9BATYtkzIJE3Ud+8WEXUmM/eyYbQmtexnfNgeM0+wKBgQDl/r/9JYVSiCHPrVAC\nGQNr0BxSdw9o0h54BZUdN2natIlopTp98YC+ZTops/+tHorjXPw5ejfX8TvFUpPy\nD0rRW65NA9W+jMUKmBrnQ+Wi9dgLEvLCeVL4dP0zzkvB7Q/cF4EiSPLNxvOYw/GG\nM1ohUFpLdfBMhznYOkKHz3y57wKBgQC34KgK5Vrl88iZk9P2pDBr2yAzC1DgEDEH\nbfN2oypBEpyxewXQL96POMnTSwcE6BmjPY9wf+iQA/H9/JFeEnuJymOT+tDW9exX\nHgxHDbBFJa4B1aB+bEkFJVS7gHD/DUSB6oWa9/8Gen9+Zih7gciNv4WNskOWulNk\nbqabWYVhgwKBgQCUmSakQWTFcS0fSCQEZvLd6qUR5tju6atD8p9oNBBRfQm2seJ7\n0thSq4aLwT91M+Gais5vuHZyL+tlTzhFUfoOEEUqf0rPhZYdhS8EssqgomSGqyRr\n4AVqf/PEUAqEbk0r74fAhg9SQrPKxPa8tVsLYSYl0TqDx27pNKMdqkI0wwKBgD88\n4S4WIQPSqpu+zngVkZ2WV+WWL7NPfj0q4D9d8Cs/Bmq3f5FQ1T72bdrgA8L5O8/7\nXPh41Peqk7AhC7GJs7j4xPRgnzA+lZCEgf5xw7yUL9rrqG2yOg6t/w0ZKENfQb9Y\nc6iPP8LvoCdNZQDM6rdtNbY8p6gP3pw8vcnRqOCXAoGAC1vj1AVpMKj7jRWyEz+k\nfw4/kBfdgUrmPyGD3puKXYijebUbU7AtTmLWY10STo+NlQhg4ktFMeyKWi1UJctW\n6OKs8jEybfIp8juS996j3KaK17HjXJd2lDZONx0cOrqzSSPhZjKPq8LXrwPdCHud\nb8CWJrnM0UFK8sUGG2Dvmpo=\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-ul6gx@cdf-2023.iam.gserviceaccount.com",
  "client_id": "101917337998555403449",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-ul6gx%40cdf-2023.iam.gserviceaccount.com"
}

cred_obj = firebase_admin.credentials.Certificate(config)
default_app = firebase_admin.initialize_app(cred_obj, {
	"databaseURL":"https://cdf-2023-default-rtdb.europe-west1.firebasedatabase.app"
	})

ref = db.reference("/")

def upload_dict(dict):
    ref.set(dict)

def upload_from_file(path):
    with open(path, "r") as f:
        file_contents = json.load(f)
    ref.set(file_contents)
    #print(ref.get())

if __name__ == "__main__":

    upload_from_file("C:/Users/lidet/workspace/projects/cdf_2023/data/assembly/assembly_test.json")
