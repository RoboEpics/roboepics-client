from os import mkdir
from time import sleep
from requests import get, post, put


class AuthorizationError(Exception):
    pass


class RequestError(Exception):
    pass


def needs_authorization(func):
    def inner(self, *args, **kwargs):
        if self._access_token is None:
            raise RequestError("You should call `authenticate` method before using the client!")
        return func(self, *args, **kwargs)
    return inner


class RoboEpicsClient:
    fusionauth_base_url = 'https://fusion.roboepics.com'
    roboepics_api_base_url = 'https://api.roboepics.com'
    client_id = '7126a051-baea-4fe1-bdf8-fde2fdb31f97'

    problem_id = None
    problem_enter_id = None

    def __init__(self, problem_id: int, problem_enter_id: int, roboepics_api_base_url: str = None, fusionauth_base_url: str = None,
                 client_id: str = None, auto_authenticate: bool = True):
        self.problem_id = problem_id
        self.problem_enter_id = problem_enter_id

        if roboepics_api_base_url is not None:
            self.roboepics_api_base_url = roboepics_api_base_url

        if fusionauth_base_url is not None:
            self.fusionauth_base_url = fusionauth_base_url

        if client_id is not None:
            self.client_id = client_id

        self._device_code = None
        self._access_token = None

        if auto_authenticate:
            self.authenticate()

    @property
    def header(self):
        return {'Authorization': "Bearer " + self._access_token}

    def authenticate(self):
        response = post(self.fusionauth_base_url + '/oauth2/device_authorize',
                        data={'client_id': self.client_id, 'scope': 'offline_access'})
        if response.status_code != 200:
            raise AuthorizationError

        body = response.json()
        self._device_code = body['device_code']
        interval = body['interval']
        print(f"URL: {self.fusionauth_base_url}/oauth2/device?client_id={self.client_id}&user_code={body['user_code']}")

        while True:
            sleep(interval)
            response = post(self.fusionauth_base_url + '/oauth2/token',
                            data={'client_id': self.client_id, 'device_code': self._device_code,
                                  'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})

            body = response.json()
            if response.status_code == 400 and body['error'] == 'invalid_request':
                raise AuthorizationError

            if 'access_token' in body:
                self._access_token = body['access_token']
                print("Successful Login")
                break

    @needs_authorization
    def download_dataset(self, path: str = None):
        response = get(f"{self.roboepics_api_base_url}/problem/{self.problem_id}", headers=self.header)
        if response.status_code != 200:
            raise RequestError(response.text)

        datas = response.json()['datasets']

        result = {}
        for data in datas:
            paths = []
            data_directory = '/'.join((path, data['dataset_path']))
            mkdir(data_directory)
            for file in data['file_set']:
                response = get(file['url'], stream=True)
                p = '/'.join((data_directory, file['file_name']))
                with open(p, 'wb') as fd:
                    for chunk in response.iter_content(chunk_size=128):
                        fd.write(chunk)
                paths.append(p)
            result[data['dataset_path']] = paths
        return result

    @needs_authorization
    def sync(self) -> str:
        response = post(f"{self.roboepics_api_base_url}/problem/enter/{str(self.problem_enter_id)}/sync-notebook",
                        headers=self.header)
        if response.status_code != 201:
            raise RequestError(response.text)

        return response.json()['reference']

    @needs_authorization
    def submission(self, path: str, reference: str = None) -> int:
        if reference is None:
            reference = self.sync()

        # Request an S3 pre-signed url to upload result file
        response = post(f"{self.roboepics_api_base_url}/problem/enter/{str(self.problem_enter_id)}/upload-result",
                        data={'filename': path.split('/')[-1]}, headers=self.header)
        if response.status_code != 201:
            raise RequestError(response.text)
        body = response.json()

        # Upload the result file to S3
        s3_url = body['url']
        with open(path, 'rb') as f:
            s3_response = put(s3_url, data=f)
            if s3_response.status_code != 200:
                raise RequestError(s3_response.text)

        # Create a new submission
        response = post(self.roboepics_api_base_url + f"/problem/{self.problem_id}/submissions", data={
            "reference": reference,
            "problem_enter": self.problem_enter_id
        }, headers=self.header)
        if response.status_code != 201:
            raise RequestError(response.text)

        return response.json()['id']
