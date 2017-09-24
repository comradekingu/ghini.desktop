#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2016,2017 Mario Frasca <mario@anche.no>.
#
# This file is part of ghini.desktop.
#
# ghini.desktop is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ghini.desktop is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ghini.desktop. If not, see <http://www.gnu.org/licenses/>.

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

consoleHandler = logging.StreamHandler()
logging.getLogger().addHandler(consoleHandler)
consoleHandler.setLevel(logging.DEBUG)
logging.getLogger().setLevel(logging.DEBUG)

import os.path
path = os.path.dirname(os.path.realpath(__file__))

import json

with open(os.path.join(path, 'settings.json'), 'r') as f:
    (user, pw, filename, imei2user, dburi, pic_path) = json.load(f)

import bauble.db
import bauble.utils

from bauble.plugins.garden import Location
from bauble.plugins.garden import Plant, PlantNote
from bauble.plugins.garden import Accession
from bauble.plugins.plants import Species
from bauble.plugins.plants import Genus

bauble.db.open(dburi, True, True)
session = bauble.db.Session()

q = session.query(Species).filter(Species.infrasp1 == u'sp')
q = q.join(Genus).filter(Genus.epithet == u'Zzz')
zzz = q.one()

import csv
import sys

header = ['timestamp', 'loc', 'acc_code', 'imei', 'binomial']
last_loc = None

import fileinput
for line in fileinput.input():
    sys.stdout.flush()
    obj = dict(zip(header, [i.strip() for i in unicode(line).split(':')]))
    if len(obj) < 3:
        continue  # ignore blank lines
    obj.setdefault('binomial', 'Zzz sp')
    try:
        obj['gn_epit'], obj['sp_epit'] = obj['binomial'].split(' ')
    except:
        obj['gn_epit'], obj['sp_epit'] = ('Zzz', 'sp')

    if not obj['loc']:
        obj['loc'] = last_loc
    last_loc = obj['loc']

    loc = session.query(Location).filter(Location.code == obj['loc']).one()

    genus = session.query(Genus).filter(Genus.epithet == obj['gn_epit']).one()
    if obj['sp_epit'] == u'sp':
        try:
            species = session.query(Species).filter(
                Species.genus == genus).filter(
                Species.infrasp1 == u'sp').first()
            if species != zzz:  # no hace falta mencionarlo
                sys.stdout.write('+')  # encontramos
        except:
            species = Species(genus=genus, sp=u'', infrasp1=u'sp')
            session.add(species)
            session.flush()
            if species != zzz:  # no hace falta mencionarlo
                sys.stdout.write('*')  # tuvimos que crear
    else:
        try:
            species = session.query(Species).filter(
                Species.genus == genus).filter(
                Species.epithet == obj['sp_epit']).one()
            sys.stdout.write('+')  # encontramos
        except:
            species = Species(genus=genus, sp=u'', epithet=obj['sp_epit'])
            session.add(species)
            session.flush()
            sys.stdout.write('*')  # tuvimos que crear

    try:
        q = session.query(Plant)
        q = q.join(Accession).filter(Accession.code == obj['acc_code'])
        q = q.filter(Plant.code == u'1')
        plant = q.one()
        if plant.location != loc:
            plant.location = loc
            sys.stdout.write(':')
        else:
            sys.stdout.write('.')
    except Exception, e:
        try:
            accession = session.query(Accession).filter(Accession.code == obj['acc_code']).one()
        except Exception, e:
            accession = Accession(species=species, code=obj['acc_code'])
            session.add(accession)
            sys.stdout.write('a')
        plant = Plant(accession=accession, location=loc, quantity=1, code=u'1')
        session.add(plant)
        session.flush()
        sys.stdout.write('p')
    # operación perro - mark the plant as seen today
    q = session.query(PlantNote)
    q = q.filter(PlantNote.plant == plant)
    q = q.filter(PlantNote.category == u'inventario')
    q = q.filter(PlantNote.note == obj['timestamp'][:8])
    if q.count() == 0:
        note = PlantNote(plant=plant, category=u'inventario', note=obj['timestamp'][:8])
        session.add(note)
        session.flush()

print
session.commit()
