#!/usr/bin/python

import re
import sys
import argparse

fts = {}
fgs = {}
ftes = []


FDB_UPLINK_VPORT = '0xffff'

# table type
FT_ESW_FDB = '0x4'

# actions
FT_ACTION_ALLOW   = 1 << 0
FT_ACTION_DROP    = 1 << 1
FT_ACTION_FWD     = 1 << 2
FT_ACTION_COUNT   = 1 << 3
FT_ACTION_ENCAP   = 1 << 4
FT_ACTION_DECAP   = 1 << 5


class Flow():
    def __init__(self, attr):
        self.attr = attr

    @property
    def attrs(self):
        return self.attr.copy()

    def __getitem__(self, key):
        return self.attr.get(key, None)


class FlowGroup(Flow):
    pass


class FlowTable(Flow):
    pass


class FlowTableEntry(Flow):
    @property
    def group(self):
        try:
            return fgs[self['group_id']]
        except KeyError:
            #print 'ERROR: fte without group id'
            return None

    @property
    def ethertype(self):
        self._ignore.append('outer_headers.ethertype')
        eth_type = '0x' + self['outer_headers.ethertype'][2:].zfill(4)
        # TODO: in verbose print tcp,udp,arp,etc
        return 'eth_type(%s)' % eth_type

    @property
    def mac(self):
        """
        eth(src=xxxx,dst=xxxx)
        """
        smac = ''
        dmac = ''

        def get_mac(low, high):
            mac1 = self[low] or '00'
            mac1 = mac1[2:].zfill(4)
            mac2 = self[high]

            if mac2:
                mac2 = mac2[2:]
            else:
                mac2 = '00000000'

            mac = mac2 + mac1
            mac = re.sub(r'(..)', r'\1:', mac).rstrip(':')
            return mac

        smac = get_mac('outer_headers.smac_15_0', 'outer_headers.smac_47_16')
        dmac = get_mac('outer_headers.dmac_15_0', 'outer_headers.dmac_47_16')

        self._ignore.append('outer_headers.smac_15_0')
        self._ignore.append('outer_headers.smac_47_16')
        self._ignore.append('outer_headers.dmac_15_0')
        self._ignore.append('outer_headers.dmac_47_16')

        return 'eth(src=%s,dst=%s)' % (smac, dmac)

    @property
    def in_port(self):
        self._ignore.append('misc_parameters.source_port')
        return 'in_port(%s)' % self['misc_parameters.source_port']

    @property
    def action(self):
        self._ignore.append('action')
        act = int(self['action'], 16)
        act &= ~FT_ACTION_COUNT
        act1 = ''

        if act & FT_ACTION_DROP:
            act &= ~FT_ACTION_DROP
            act1 += ',drop'
        if act & FT_ACTION_FWD:
            act &= ~FT_ACTION_FWD
            act1 = ',fwd' # TODO dst port
        if act:
            print 'ERROR: unknown action %s' % act

        act1 = act1.lstrip(',')
        return ' action:%s' % act1

    def __str__(self):
        x = []
        a = self.attrs

        self._ignore = [
            'group_id',
            'table_id',
            'flow_index',
            'gvmi',
            'valid',
            'flow_counter_list_size', # TODO: get counter
            'flow_counter[0].flow_counter_id',
            'flow_counter[1].flow_counter_id',
        ]

        x.append(self.in_port)
        x.append(self.mac)
        x.append(self.ethertype)
        x.append(self.action)

        # find unmatches attrs
        for i in self._ignore:
            if i in a:
                del a[i]

        if a:
            print '  -Missed: %s' % ', '.join(a)

        return ','.join(x)


def parse_args():
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', required=True,
                        help='Inpurt sample file')
    return parser.parse_args()


def main():
    args = parse_args()

    # - FG :gvmi=0x0,table_id=8,group_id=0x0 -
    group_re = re.compile('\s*- ([\w]+) :([\w,=]+)')
    group_keys_re = re.compile('(?:(\w+)=(\w+)),?')

    # action                                                                          :0x4
    # valid                                                                           :0x1
    # group_id                                                                        :0x00000004
    # destination_list_size                                                           :0x1
    # destination[0].destination_id                                                   :0x89
    # destination[0].destination_type                                                 :TIR (0x2)

    with open(args.sample, 'r') as f:
        data = f.read().split("\n\n")

    # parse data
    for block in data:
        block = block.strip()
        m = re.match(group_re, block)
        if not m:
            continue
        group = m.groups()[0]
        keys = re.findall(group_keys_re, m.groups()[1])
        attr = {}
        for item in keys:
            attr[item[0]] = item[1]
        block1 = '\n'.join(block.splitlines()[1:])
        d = re.findall('([^\s]+)\s+:(.*)', block1)
        for item in d:
            attr[item[0]]= item[1]

        if 'group_id' in attr:
            attr['group_id'] = int(attr['group_id'], 0)

        if group == 'FG':
            fg = FlowGroup(attr)
            fgs[fg['group_id']] = fg
        elif group == 'FT':
            ft = FlowTable(attr)
            fts[ft['table_id']] = ft
        elif group == 'FTE':
            fte = FlowTableEntry(attr)
            ftes.append(fte)
        else:
            print 'ERROR: unknown type %s' % group

    # dump
    for fte in ftes:
        if len(fte['table_id']) < 4:
            # TODO: we currently only want the rules we add from ovss
            # we create new fdb table which gets a high id number.
            continue

        print fte


if __name__ == "__main__":
    main()
