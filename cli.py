#!/usr/bin/env python
# coding: utf-8

import os
import sys
import time
import atexit
import signal
from datetime import datetime
import threading
import rabbitpy


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


class StampedOut(object):
    def __init__(self, std):
        super(StampedOut, self).__init__()
        self.std = std
        self._flag = True
        atexit.register(self.close)

    def write(self, x):
        if x == '\n':
            self.std.write(x)
            self._flag = True
            self.flush()
        elif self._flag is True:
            self.std.write('[%s] %s' % (str(datetime.now()), x))
            self._flag = False
        else:
            self.std.write(x)

    def flush(self):
        self.std.flush()
        os.fsync(self.std.fileno())

    def close(self):
        if self.std is not None:
            self.std.close()
            self.std = None


class BaseDaemon(object):
    def __init__(self, pidfile, stdin=os.devnull,
                stdout=os.devnull, stderr=os.devnull,
                home_dir='.', umask=022, verbose=1, use_gevent=False):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
        self.home_dir = home_dir
        self.verbose = verbose
        self.umask = umask
        self.daemon_alive = True
        self.use_gevent = use_gevent

    def daemonize(self):
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write(
                "fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        os.chdir(self.home_dir)
        os.setsid()
        os.umask(self.umask)
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write(
                "fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        if sys.platform != 'darwin':  # This block breaks on OS X
            sys.stdout.flush()
            sys.stderr.flush()
            si = file(self.stdin, 'r')
            so = file(self.stdout, 'a+')
            if self.stderr:
                se = file(self.stderr, 'a+', 0)
            else:
                se = so
            os.dup2(si.fileno(), sys.stdin.fileno())
            # os.dup2(so.fileno(), sys.stdout.fileno())
            # os.dup2(se.fileno(), sys.stderr.fileno())

            sys.stdout = StampedOut(so)
            sys.stderr = StampedOut(se)

        def sigtermhandler(signum, frame):
            self.daemon_alive = False
            sys.exit()

        if self.use_gevent:
            import gevent
            gevent.reinit()
            gevent.signal(signal.SIGTERM, sigtermhandler, signal.SIGTERM, None)
            gevent.signal(signal.SIGINT, sigtermhandler, signal.SIGINT, None)
        else:
            signal.signal(signal.SIGTERM, sigtermhandler)
            signal.signal(signal.SIGINT, sigtermhandler)

        if self.verbose >= 1:
            print "Started"
        atexit.register(
            self.delpid)  # Make sure pid file is removed if we quit
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        os.remove(self.pidfile)

    def start(self, *args, **kwargs):
        if self.verbose >= 1:
            print "Starting..."
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
        except SystemExit:
            pid = None

        if pid:
            message = "pidfile %s already exists. Is it already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)
        self.daemonize()
        self.run(*args, **kwargs)

    def stop(self):
        if self.verbose >= 1:
            print "Stopping..."
        pid = self.get_pid()
        if not pid:
            message = "pidfile %s does not exist. Not running?\n"
            sys.stderr.write(message % self.pidfile)
            if os.path.exists(self.pidfile):
                os.remove(self.pidfile)
            return  # Not an error in a restart
        try:
            i = 0
            while 1:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)
                i = i + 1
                if i % 10 == 0:
                    os.kill(pid, signal.SIGHUP)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

        if self.verbose >= 1:
            print "Stopped"

    def restart(self):
        self.stop()
        self.start()

    def get_pid(self):
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
        except SystemExit:
            pid = None
        return pid

    def is_running(self):
        pid = self.get_pid()

        if pid is None:
            print 'Process is stopped'
        elif os.path.exists('/proc/%d' % pid):
            print 'Process (pid %d) is running...' % pid
        else:
            print 'Process (pid %d) is killed' % pid

        return pid and os.path.exists('/proc/%d' % pid)

    def run(self):
        raise NotImplementedError


class MqClient(object):
    """连接mq，初始化队列，并监听队列"""
    def __init__(self, addr, queue):
        super(MqClient, self).__init__()
        self.addr = addr
        self.q_name = queue
        self.conn = None
        self.ch = None
        self.queue = rabbitpy.Queue(self.channel(), self.q_name)
        self.queue.declare()

    def close(self):
        if self.ch is not None:
            self.ch.close()
            self.ch = None
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def connect(self):
        if self.conn is None:
            self.conn = rabbitpy.Connection(self.addr)
        if self.conn.STATES[self.conn.state] not in ('Open', 'Opening'):
            self.conn.close()
            self.conn = rabbitpy.Connection(self.addr)
        return self.conn

    def channel(self):
        if self.ch is None:
            self.ch = self.connect().channel()
        if self.ch.STATES[self.ch.state] not in ('Open', 'Opening'):
            self.ch.close()
            self.ch = self.connect().channel()
        return self.ch

    def init_mq(self):
        self.queue = rabbitpy.Queue(self.channel(), self.q_name)
        self.queue.declare()

    def send_msg(self, queue, msg, properties={}):
        message = rabbitpy.Message(self.channel(), msg, properties=properties)
        message.publish('', queue)


class CmsClient(threading.Thread):
    """获取电脑mac，生成固定序列号，型号，处理消息同步"""
    # CmsClient(cms_addr, model, sn, mac)
    def __init__(self, cms_addr, model, sn):
        super(CmsClient, self).__init__()
        self.reconnet = False
        self.cms_addr = cms_addr
        self.sn = sn
        self.model = model
        self.queue = '%s|%s' % (self.sn, self.model)
        self.mq_client = MqClient(cms_addr, self.queue)
        self.ssh_client = None
        self.ip = '192.168.0.100'
        self.mac = '123412341234'
        self.start_time = int(time.time())
        self.login_state = False

    def login_cms(self):
        data = {
            "event": "login", "api_ver": "1.0",
            "data": {
                "dev_sn": self.sn,
                "dev_type": "ROUTER",
                "dev_mfr": "ruijie",
                "dev_model": self.model,
                "hw_ver": '1.0',
                "dev_uptime": int(time.time()) - self.start_time,
                "soft_ver": '2.8.0',
            }
        }
        properties = {"reply_to": self.queue}
        # print 'cms login data :%s' % data
        self.mq_client.send_msg('dev_login_q', data, properties)

    def run(self):
        consumer = threading.Thread(target=self.listener)
        consumer.setDaemon(True)
        consumer.start()

        while 1:
            # self.login_cms()
            time.sleep(1)
            # if self.login_state is False:
            #     self.login_cms()
            # if self.reconnet:
            #     break
            # time.sleep(5)

        self.mq_client.close()
        self.mq_client = None
        print 'cli %s stoped' % self.sn

    def listener(self):
        for msg in self.mq_client.queue.consume(no_ack=True):
            if msg is None:
                print 'none msg...'
                self.reconnet = True
                break
            # else:
            #     if self.handle_msg(msg) is True:
            #         self.reconnet = True
            #         break

    def handle_msg(self, msg):
        # print 'recieve msg: %s' % msg.body
        # 登录成功 同步client状态
        try:
            data = msg.json()
        except:
            print 'msg json error'
            return
        if data.get('event') == 'login':
            if data.get('status') == 0:
                _data = {
                    "dev_sn": self.sn,
                    "wan": {
                        "wan1": {
                            "link": "up",
                            "proto": "static",
                            "ipaddr": self.ip,
                            "macaddr": self.mac,
                            "http_port": "3388"
                        }
                    },
                    "user": {
                        "password": "admin",
                        "username": "root"
                    }
                }
                self.login_state = True
                # print 'sync data %s' % _data
                self.mq_client.send_msg('data_sync', _data)


class Daemon(BaseDaemon):
    """docstring for Daemon"""
    def __init__(self, pidfile, stdout, stderr):
        super(Daemon, self).__init__(pidfile, stdout=stdout, stderr=stderr)
        self.rabbit_server = '192.168.120.108'
        self.vhost = 'v2'

    def run(self):
        # 序列号开头8位，型号，并发数量，sn开始序号在init中定义
        if self.check_cli_ini() is not True:
            print 'please check cli.ini, and restart service'
            return
        self.timeout = 3000
        cms_addr = 'amqp://remote:remote@%s:5672/%s' % (self.rabbit_server, self.vhost)
        device_pool = {}
        for i in xrange(self.begin_sn, self.end_sn + 1):
            sn = '%s%05d' % (self.base_sn, i)
            t = CmsClient(cms_addr, self.model, sn)
            t.setDaemon(True)
            device_pool[sn] = t

        for i in device_pool.values():
            i.start()
        while 1:
            for k, v in device_pool.iteritems():
                if not v.is_alive():
                    print '%s client had dead. restarting' % k
                    v = device_pool.pop(k)
                    del v
                    t = CmsClient(cms_addr, self.model, sn)
                    t.setDaemon(True)
                    device_pool[k] = t
                    t.start()
                time.sleep(5)

    def check_cli_ini(self):
        import ConfigParser
        cf = ConfigParser.ConfigParser()
        cf.read(os.path.join(BASE_DIR, 'cli.ini'))
        opts = cf.options("base")
        if set(['model', 'base_sn', 'begin_sn', 'end_sn']) != set(opts):
            print 'miss [base] option: model base_sn begin_sn end_sn'
            return
        self.model = cf.get("base", "model")
        self.base_sn = cf.get("base", "base_sn")
        begin_sn = cf.get("base", "begin_sn")
        end_sn = cf.get("base", "end_sn")
        if not all((self.model, self.base_sn, begin_sn, end_sn)):
            print 'please set [base] option: model base_sn begin_sn end_sn'
            return
        try:
            self.begin_sn = int(begin_sn)
            self.end_sn = int(end_sn)
        except Exception as e:
            print 'option: begin_sn and end_sn must be integer'
            return
        return True


if __name__ == '__main__':
    log_path = os.path.join(BASE_DIR, 'log.log')
    error_path = os.path.join(BASE_DIR, 'error.log')
    daemon = Daemon('/tmp/stress.pid', log_path, error_path)

    if len(sys.argv) == 2:
        cmd = sys.argv[1]
        if 'start' == cmd:
            daemon.start()
        elif 'stop' == cmd:
            daemon.stop()
        elif 'restart' == cmd:
            daemon.restart()
        else:
            print 'Unknown command'
            sys.exit(2)
        sys.exit(0)
    else:
        print 'Usage: start|stop|restart'
        sys.exit(2)
