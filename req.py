# coding: utf-8
import time
import requests


def main():
	while 1:
		requests.get('http://10.233.1.7/login')
		time.sleep(0.001)


if __name__ == '__main__':
	main()
