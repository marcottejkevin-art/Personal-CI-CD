from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return {
        "application": "My CI/CD Demo",
        "message": "Hello from my CI/CD pipeline!",
        "status": "running"
    }


@app.route("/health")
def health():
    return {
        "status": "healthy"
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
