from flask.Response import BaseResponse

class Response(BaseResponse):

    status_code: int
    mimetype: str
    body: str


    def __init__(self, body: str, mimetype: str, status_code: int):
        self.body = body
        self.mimetype = mimetype
        self.status_code = status_code
    
    def __str__(self) -> str:
        data = {
            "body" : self.body,
            "mimetype" : self.mimetype,
            "status_code": self.status_code
        }
        return data