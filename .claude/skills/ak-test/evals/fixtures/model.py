def authorized(user, tenant):
    return user is not None and user["tenant"] == tenant

def download(data, mode):
    if mode == "csv":
        return ",".join(data)
    if mode == "json":
        raise ValueError("unsupported format")
    raise ValueError(mode)

def quota(count):
    return count < 4
