#automatically generated by the clientobjectgenerator
from clientproxy import *

class Jobmanager():
	def __init__(self):
		invoke_command(self, "__init__")

	def __str__(self):
		invoke_command(self, "__str__")

	def add_job(self, args):
		invoke_command(self, "add_job", args)

	def list_jobs(self):
		invoke_command(self, "list_jobs")

	def remove_job(self, args):
		invoke_command(self, "remove_job", args)
