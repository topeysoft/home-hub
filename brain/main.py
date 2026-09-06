import logging, uvicorn
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
if __name__ == "__main__":
    uvicorn.run("hub.api:app", host="0.0.0.0", port=8300, reload=False)
