'''
@author: Deniz Altinbuken, Emin Gun Sirer
@note: ConCoord Client Proxy
@copyright: See LICENSE
'''
import socket, os, sys, time, random, threading, select
from threading import Thread, Condition, RLock, Lock
import pickle
from pack import *
from concoord.enums import *
from concoord.utils import *
from concoord.exception import *
from concoord.connection import ConnectionPool, Connection
from concoord.message import *
from concoord.pvalue import PValueSet
try:
    import dns
    import dns.resolver
    import dns.exception
except:
    print("Install dnspython: http://www.dnspython.org/")

REPLY = 0
CONDITION = 1

class ClientProxy():
    def __init__(self, bootstrap, timeout=60, debug=False, token=None):
        self.debug = debug
        self.timeout = timeout 
        self.domainname = None
        self.token = token
        self.socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.writelock = Lock()

        self.bootstraplist = self.discoverbootstrap(bootstrap)
        if len(self.bootstraplist) == 0:
            raise ConnectionError("No bootstrap found")
        if not self.connecttobootstrap():
            raise ConnectionError("Cannot connect to any bootstrap")
        myaddr = findOwnIP()
        myport = self.socket.getsockname()[1]
        self.me = Peer(myaddr,myport,NODE_CLIENT)
        self.commandnumber = random.randint(1, sys.maxint)

    def getipportpairs(self, bootaddr, bootport):
        for node in socket.getaddrinfo(bootaddr, bootport):
            yield (node[4][0],bootport)

    def getbootstrapfromdomain(self, domainname):
        tmpbootstraplist = []
        try:
            answers = dns.resolver.query('_concoord._tcp.'+domainname, 'SRV')
            for rdata in answers:
                for peer in self.getipportpairs(str(rdata.target), rdata.port):
                    if peer not in tmpbootstraplist:
                        tmpbootstraplist.append(peer)
        except (dns.resolver.NXDOMAIN, dns.exception.Timeout):
            if self.debug:
                print "Cannot resolve name"
        return tmpbootstraplist

    def discoverbootstrap(self, givenbootstrap):
        tmpbootstraplist = []
        try:
            for bootstrap in givenbootstrap.split(","):
                # The bootstrap list is read only during initialization
                if bootstrap.find(":") >= 0:
                    bootaddr,bootport = bootstrap.split(":")
                    for peer in self.getipportpairs(bootaddr, int(bootport)):
                        if peer not in tmpbootstraplist:
                            tmpbootstraplist.append(peer)
                else:
                    self.domainname = bootstrap
                    tmpbootstraplist = self.getbootstrapfromdomain(self.domainname)
        except ValueError:
            if self.debug:
                print "bootstrap usage: ipaddr1:port1,ipaddr2:port2 or domainname"
            self._graceexit()
        return tmpbootstraplist

    def connecttobootstrap(self):
        connected = False
        for boottuple in self.bootstraplist:
            try:
                self.socket.close()
                self.socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                self.socket.connect(boottuple)
                self.conn = Connection(self.socket)
                self.conn.settimeout(CLIENTRESENDTIMEOUT)
                self.bootstrap = boottuple
                connected = True
                if self.debug:
                    print "Connected to new bootstrap: ", boottuple
                break
            except socket.error, e:
                if self.debug:
                    print e
                continue
        return connected

    def trynewbootstrap(self):
        if self.domainname:
            self.bootstraplist = self.getbootstrapfromdomain(self.domainname)
        else:
            oldbootstrap = self.bootstraplist.pop(0)
            self.bootstraplist.append(oldbootstrap)
        return self.connecttobootstrap()

    def invoke_command(self, *args):
        # create a request descriptor
        senddone = False
        sendcount = -1
        lastreplycode = -1
        self.commandnumber += 1
        while True:
            sendcount += 1
            clientmsg = create_message(MSG_CLIENTREQUEST, self.me,
                                       {FLD_PROPOSAL: Proposal(self.me, self.commandnumber, args), 
                                        FLD_TOKEN: self.token,
                                        FLD_SENDCOUNT: sendcount})
            
            # send the request
            if not senddone:
                success = self.conn.send(clientmsg)
                if not success:
                    self.reconfigure()
                    continue
                senddone = True
        # Receive reply
            try:
                for reply in self.conn.received_bytes():
                    if reply and reply.type == MSG_CLIENTREPLY:
                        if reply.replycode == CR_OK:
                            return reply.reply
                        elif reply.replycode == CR_UNBLOCK:
                            # actionable response, wake up the thread
                            assert lastreplycode == CR_BLOCK, "unblocked thread not previously blocked"
                            return reply.reply
                        elif reply.replycode == CR_EXCEPTION:
                            raise Exception(reply.reply)
                        elif reply.replycode == CR_INPROGRESS or reply.replycode == CR_BLOCK:
                            # the thread is already waiting, no need to do anything
                            lastreplycode = reply.replycode
                            # go wait for another message
                            continue
                        elif reply.replycode == CR_REJECTED or reply.replycode == CR_LEADERNOTREADY:
                            self.reconfigure()
                            continue
                        else:
                            print "should not happen -- unknown response type"
            except ConnectionError:
                self.reconfigure()
                continue
            except KeyboardInterrupt:
                self._graceexit()

    def reconfigure(self):
        if not self.trynewbootstrap():
            raise ConnectionError("Cannot connect to any bootstrap")
            
    def _graceexit(self):
        os._exit(0)
