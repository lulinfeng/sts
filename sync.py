# coding:utf-8
import os
import time
import threading
import paramiko
from clilist import client_list

SPAN = 900


ssh = paramiko.SSHClient()
ssh.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def set_client_count(start, end, host):
	stdin, stdout, stderr = ssh.exec_command('sed -i "s/begin_sn.*/begin_sn = %d/" sts/cli.ini' % start)
	_err = stderr.read()
	if _err:
		print ('set begin_sn meet error', host)
		print _err
	stdin, stdout, stderr = ssh.exec_command('sed -i "s/end_sn.*/end_sn = %d/" sts/cli.ini' % end)
	_err = stderr.read()
	if _err:
		print ('set end_sn meet error', host)
		print _err


def sftp():
	sftp = ssh.open_sftp()
	sftp.put('./cli.py', './sts/cli.py')


def start_client(ssh, host):
	# && echo>error.log && echo>log.log
	i, o, e = ssh.exec_command('ulimit -n 65536 && echo>sts/error.log && echo>sts/log.log && python sts/cli.py start')
	_e = e.read()
	if _e:
		print ('start %s client error:' % host, _e)
	else:
		print o.read()


def stop_client(host):
	i, o, e = ssh.exec_command('python sts/cli.py stop')
	_e = e.read()
	if _e:
		print ('stop %s client error:' % host, _e)
	else:
		print host, o.read()


def show_client_ini(host):
	i, o, e = ssh.exec_command('cat sts/cli.ini')
	_e = e.read()
	if _e:
		print ('get %s client ini error:' % host, _e)
	else:
		print o.read()


def start_cli(ssh, host):
	t = threading.Thread(target=start_client, args=(ssh, host))
	t.start()
	# t.join()


def reboot(host):
	stdin, stdout, stderr = ssh.exec_command('reboot')
	_err = stderr.read()
	if _err:
		print ('reboot %s meet error' % host, _err)
		print _err


def run_command(host, cmd):
	stdin, stdout, stderr = ssh.exec_command(cmd)
	_err = stderr.read()
	if _err:
		print ('run command %s meet error' % host, _err)
		print _err
	else:
		print host, stdout.read()


def run():
	cmd = 'cat ~/sts/error.log'
	for index, host in enumerate(client_list):
		ssh.connect(host, username='root')
		# set_client_count(index * SPAN + 1, (index + 1) * SPAN, host)
		# sftp()
		stop_client(host)
		# start_cli(ssh, host)
		# show_client_ini(host)
		# run_command(host, cmd)
	time.sleep(5)
	ssh.close()

run()

print 'ok'
