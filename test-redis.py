import redis

r = redis.Redis(host='localhost', port=6379, db=0)
r.set('test', 'connection')
print(r.get('test').decode('utf-8'))