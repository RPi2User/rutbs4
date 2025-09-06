from flask.wrappers import Response as BaseResponse
import json

class Response(BaseResponse):
    
    def _asdict(self) -> dict:
        data = {
            "response_body" : str(self.response),
            "mimetype" : self.mimetype,
            "status_code": self.status
        }
        return data

    def __str__(self) -> str:
        data = {
            "response_body" : str(self.response),
            "mimetype" : self.mimetype,
            "status_code": self.status
        }
        return json.dumps(data)