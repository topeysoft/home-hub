import logging, os, uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

if __name__ == "__main__":
    # HUB_RELOAD=1 restarts the hub whenever anything under hub/ changes. For development only, and
    # worth having because the failure it prevents is SILENT: a hub left running from an hour ago
    # serves an older shape of /ambient or /home, the panel renders it without complaint, and the
    # bug looks like a panel bug. Nothing on the screen says the brain is stale.
    #
    # reload_dirs is not optional here. The hub writes settings.json, events.db, rules.json and
    # phones.json into brain/ itself, so a watcher pointed at the whole directory would restart the
    # house every time it logged an event -- which is every time anything in it moves.
    reload = os.environ.get("HUB_RELOAD") == "1"
    uvicorn.run("hub.api:app", host="0.0.0.0", port=int(os.environ.get("HUB_PORT", "8300")),
                reload=reload, reload_dirs=["hub"] if reload else None)
