from time import sleep
from requests import post, get


class RoboepicsClient():
    def __init__(self, problem_enter_id):
        self._fusion_base_url = 'https://fusion.roboepics.com'
        self._roboepics_api_base_url = 'https://api.roboepics.com'
        self._client_id = '7126a051-baea-4fe1-bdf8-fde2fdb31f97'
        self._device_code = None
        self._access_token = None
        self._problem_enter_id = None
        self._header = {'Authorization': None}
        self.device_authorize()

    def device_authorize(self):
        response = post(self._fusion_base_url + '/oauth2/device_authorize',
                        data={'client_id': self._client_id, 'scope': 'offline_access'})
        if response.status_code == 200:
            body = response.json()
            self._device_code = body['user_code']
            print("URL : " + self._fusion_base_url + "/oauth2/device?client_id=" +
                  self._client_id, " Code : "+self._device_code)

            response = post(self._fusion_base_url + '/oauth2/token', data={
                'client_id': self._client_id, 'device_code': self._device_code, 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            })
            if response.status_code == 200:
                body = response.json()
                while True:
                    if 'access_token' in body:
                        self._access_token = body['access_token']
                        self._header['Authorization'] = 'Bearer ' + \
                            self._access_token
                        print("Successful Login")
                        break

    def commit(self):
        response = post(self._roboepics_api_base_url+"/problem/enter/" +
                        self._problem_enter_id+"/commit", data={}, headers=self._header)
        if response.status_code == 200:
            body = response.json()
            return body['refrence']

    def submission(self, path):
        refrence = self.commit()
        response = post(self._roboepics_api_base_url+"/problem/enter/"+self._problem_enter_id+"/upload", data={}, headers=self._header})
        if response.status_code == 200:
            body = response.json()
            s3_url = body['url']
            with open(path, 'rb') as f:
                s3_response = post(url=s3_url, files={'file': (path, f)})
                if s3_response.status_code == 204:
                    response = post(self._roboepics_api_base_url+"/problem/submission", data={
                        "refrence": refrence,
                        "problem_enter_id": self._problem_enter_id
                    })
                    if response.status_code == 200:
                        return response.json()
