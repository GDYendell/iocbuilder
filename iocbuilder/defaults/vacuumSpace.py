from iocbuilder import Substitution, ModuleBase
from iocbuilder.arginfo import *

from iocbuilder.modules.digitelMpc import \
    digitelMpcIonp, digitelMpcIonpGroup, dummyIonp
from iocbuilder.modules.mks937a import \
    mks937aGauge, mks937aGaugeGroup, \
    mks937aImg, mks937aImgGroup, mks937aImgDummy, \
    mks937aPirg, mks937aPirgGroup
from iocbuilder.modules.vacuumValve import \
    valve, vacuumValveGroup, dummyValve

class space(Substitution):
    '''Helper that packages up a series of ion pumps, gauges, imgs, pirgs and
    valves, groups them together, and creates a vacuum space out of them'''
    # this is the number we give to the next autogenerated group
    spacei = 99
    # this is the number of objects we allow in each group
    numobs = 4

    def __lookup_prefix(self, ob):
        # lookup the device prefix of an object
        if ob.args.has_key('device'):
            return ob.args['device']
        else:
            # this is a gauge
            return '%s-VA-GAUGE-%s'%(ob.args['dom'],ob.args['id'])

    def __init__(self, device, ionps = [None], gauges = [None], 
            imgs = [None], pirgs = [None], valves = [None], name = ''):
        # these are the different types of component we deal with
        components = dict(
            ionp = (digitelMpcIonpGroup, dummyIonp),
            gauge = (mks937aGaugeGroup,   None),
            img = (mks937aImgGroup,     mks937aImgDummy),
            pirg = (mks937aPirgGroup,    None),
            valve = (vacuumValveGroup,    dummyValve))

        # this is what we'll pass as the space.template arguments
        argdict = dict(device=device, name=name)
        
        # loop over the component types
        for component, (group, dummy) in components.items():
            # grab the list of objects of this type
            l = [ x for x in locals()[component+'s'] if x != None ]
            # work out a prefix for this component type
            p = '%s-VA-%s-%02i' % (
                device.split('-')[0], component.upper(), space.spacei)
            if len(l)==0:
                # need to make dummy objects
                assert dummy != None, \
                    '%s: Vacuum space defined with missing %s' % (
                        device, component)
                ob = dummy(device=p)
                argdict[component] = p
            elif len(l)==1:
                # only one object exists
                argdict[component] = self.__lookup_prefix(l[0])
            else:
                # many objects exist, so make a group for them
                d = dict(device=p)
                if component == 'ionp':
                    d['delay'] = 4
                elif component == 'valve':
                    d['delay'] = 1
                # pad the list of objects to length 8 with the first ob
                l = (l + [l[0]]*8)[:8]
                for j,o in enumerate(l):
                    d['%s%i' % (component, j+1)] = self.__lookup_prefix(o)
                # create a group of all these objects
                group(**d)
                argdict[component] = p       
        
        # finally decrement the space number and init the substitution     
        space.spacei -= 1
        self.__super.__init__(**argdict)

    ArgInfo = makeArgInfo(__init__,
        device = Simple('Device Prefix', str),
        ionps  = List  ('Ionp objects',  numobs, Ident, digitelMpcIonp),        
        gauges = List  ('Gauge objects', numobs, Ident, mks937aGauge),
        imgs   = List  ('Img objects',   numobs, Ident, mks937aImg),
        pirgs  = List  ('Pirg objects',  numobs, Ident, mks937aPirg),        
        valves = List  ('Pirg objects',  numobs, Ident, valve),
        name   = Simple('Object name', str))        

    # Substutution attributes
    Arguments = ['name', 'device', 'ionp', 'gauge', 'img', 'pirg', 'valve']
    TemplateFile = 'space.template'

