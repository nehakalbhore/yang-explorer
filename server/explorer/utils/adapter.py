"""
    Copyright 2015, Cisco Systems, Inc

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    @author: Pravin Gohite, Cisco Systems, Inc.
    @author: Michael Ott, Cisco Systems, Inc.
"""

import json
import logging
from collections import OrderedDict
import lxml.etree as ET
from explorer.utils.netconf import gen_netconf
from explorer.utils.restconf import gen_restconf
from explorer.utils.runner import NCClient, RestClient


class Adapter(object):
    """ Class adapter for NCClient """
    @staticmethod
    def parse_request(payload):
        """ Parse user request """

        request = ET.fromstring(payload)
        protocol = request.get('protocol', None)
        fmt = request.get('format', 'xpath')
        rpc = None
        auth = {}
        for child in request:
            tag = child.xpath('local-name()')
            if tag == 'device-auth':
                auth['platform'] = child.get('platform', None)
            elif tag == 'netconf-auth':
                auth['host'] = child.get('host', None)
                auth['port'] = int(child.get('port', 830))
                auth['user'] = child.get('user', None)
                auth['passwd'] = child.get('passwd', None)
            elif tag == 'raw':
                if protocol == 'netconf':
                    rpc = ET.fromstring(child.text)
                else:
                    rpc = child.text
            elif tag == 'keyvalue' and len(child):
                rpc = ''

        return protocol, auth, fmt, rpc

    @staticmethod
    def run_request(username, payload):
        """
        Execute a RPC request using NCClient
        """
        logging.debug('run_request (%s)' % username)

        # hack
        payload = payload.replace('<metadata>', '')
        payload = payload.replace('</metadata>', '')

        protocol, device, fmt, rpc = Adapter.parse_request(payload)
        if device.get('host', None) is None:
            reply = ET.Element('reply')
            reply.text = 'Device info missing'
            logging.error("Device information is not provided in request payload")
            return reply

        if fmt == 'xpath' and rpc == '':
            rpc = Adapter.gen_rpc(username, payload)

        logging.debug("run_request: Protocol %s, Host %s, Port %s, User %s" %
                      (protocol, device['host'], device['port'], device['user']))

        if protocol == 'netconf':
            return Adapter.run_netconf(username, device, rpc)
        elif protocol == 'restconf':
            return Adapter.run_restconf(username, device, rpc)

        reply = ET.Element('reply')
        reply.text = 'Invalid protocol in the payload'
        return reply

    @staticmethod
    def run_netconf(username, device, rpc):
        """ Execute Netconf request """

        plat = device.get('platform', None)
        if plat is not None and plat not in ['', 'other']:
            params = {'name' : plat}
        else:
            params = {}

        session = NCClient(device['host'], device['port'],
                           device['user'], device['passwd'], params)

        # If rpc is not provided, return capabilities
        if rpc is None or rpc  == '':
            return session.get_capability()

        logging.debug("run_netconf: " + ET.tostring(rpc))
        return session.run(ET.tostring(rpc))

    @staticmethod
    def run_restconf(username, device, msg):
        """ Execute Restconf request """

        session = RestClient(device)
        if session is None:
            reply = ET.Element('reply')
            reply.text = 'Could not create session for %s' % protocol
            return reply

        if isinstance(msg, str):
            msg = json.loads(msg)

        url = 'http://' + device['host'] + ':' + str(device['port'])
        if msg is None or msg  == '':
            return session.get_capability(url)

        msg['url'] = url + msg['url']
        return session.run(msg)

    @staticmethod
    def gen_rpc(username, payload):
        """
        Generate Netconf / Restconf RPC
        """
        if payload == '':
            logging.debug('gen_rpc: Rcvd: ' + 'None')
            return None

        logging.debug('gen_rpc: Rcvd: ' + payload)

        request = ET.fromstring(payload)
        protocol = request.get('protocol', None)
        if protocol is None:
            logging.error('gen_rpc: Invalid payload, protocol missing !!')
            return None

        rpc = None
        if protocol == 'restconf':
            res = Adapter._gen_rpc(username, request)
            ''' returns json '''
            return build_response(res)
        else:
            rpc = Adapter._gen_rpc(username, request)

        logging.info('gen_rpc: Generated : ' + rpc)
        ''' returns xml '''
        return ET.fromstring(rpc)

    @staticmethod
    def _gen_rpc(username, request, mode = ''):
        """ Wrapper for rest & netconf module """
        protocol = request.get('protocol', '')
        if mode == '': mode = request.get('operation', '')

        # Generate RESTCONF
        if protocol == 'restconf':
            return gen_restconf(username, request, mode)

        # Generate NETCONF
        return gen_netconf(username, request, mode)


def build_response(res):
    rest_ops = {"merge": "PATCH",
                "create": "POST",
                "replace": "PUT",
                "delete": "DELETE",
                "get": "GET"}
    msg = OrderedDict()
    for r in res:
        op, url, data, hdr = r
        msg['method'] = str(rest_ops.get(op, op))
        msg['url'] = url
        msg['params'] = hdr
        msg['data'] = json.loads(data, object_pairs_hook=OrderedDict)

    reply = json.dumps(msg, indent=3, separators=(',', ': '))
    logging.debug('Json: ' + reply)
    return reply
