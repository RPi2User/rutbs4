from flask.wrappers import Response as BaseResponse
import json

class Response(BaseResponse):

    """
    def __init__(self, body: str, mimetype: str, status_code: int):
        self = BaseResponse(response=body, status=status_code, mimetype=mimetype)
        self.body = self.response
        self.status_code = self.status
    """
    
    def _asdict(self) -> dict:
        data = {
            "response_body" : str(self.response),
            "mimetype" : self.mimetype,
            "status_code": self.status
        }
        print("RESPONSE DEBUG: -----------------------------")
        print(data)
        return data

    def __str__(self) -> str:
        data = {
            "response_body" : str(self.response),
            "mimetype" : self.mimetype,
            "status_code": self.status
        }
        return json.dumps(data)