#
# Genera table module
#

import os, traceback
import gtk
from sqlalchemy import *
from sqlalchemy.orm.session import object_session
from sqlalchemy.exceptions import SQLError
import bauble
from bauble.editor import *
import bauble.utils as utils
from bauble.types import Enum
from bauble.utils.log import debug

# TODO: should be a higher_taxon column that holds values into 
# subgen, subfam, tribes etc, maybe this should be included in Genus

# TODO: since there can be more than one genus with the same name but
# different authors we need to show the Genus author in the result search
# and at least give the Genus it's own infobox, we should also check if
# when entering a plantname with a chosen genus if that genus has an author
# ask the user if they want to use the accepted name and show the author of
# the genus then so they aren't using the wrong version of the Genus,
# e.g. Cananga

def edit_callback(row):
    value = row[0]
    
    # TODO: the select paramater can go away when we move FamilyEditor to the 
    # new style editors    
    e = GenusEditor(model_or_defaults=value)
    return e.start() != None


def add_species_callback(row):
    from bauble.plugins.plants.species_editor import SpeciesEditor
    value = row[0]
    # call with genus_id instead of genus so the new species doesn't get bound
    # to the same session as genus
    # TODO: i wish there was a better way around this
    e = SpeciesEditor(model_or_defaults={'genus_id': value.id})
    return e.start() != None


def remove_callback(row):
    value = row[0]
    s = '%s: %s' % (value.__class__.__name__, str(value))
    msg = "Are you sure you want to remove %s?" % s
        
    if utils.yes_no_dialog(msg):
        from sqlobject.main import SQLObjectIntegrityError
        try:
            value.destroySelf()
            # since we are doing everything in a transaction, commit it
            sqlhub.processConnection.commit() 
            return True
        except SQLObjectIntegrityError, e:
            msg = "Could not delete '%s'. It is probably because '%s' "\
                  "still has children that refer to it.  See the Details for "\
                  " more information." % (s, s)
            utils.message_details_dialog(msg, str(e))
        except:
            msg = "Could not delete '%s'. It is probably because '%s' "\
                  "still has children that refer to it.  See the Details for "\
                  " more information." % (s, s)
            utils.message_details_dialog(msg, traceback.format_exc())


genus_context_menu = [('Edit', edit_callback),
                       ('--', None),
                       ('Add species', add_species_callback),
                       ('--', None),
                       ('Remove', remove_callback)]


def genus_markup_func(genus):
    '''
    '''
    return '%s (%s)' % (str(genus), str(genus.family))

    '''
    hybrid: indicates whether the name in the Genus Name field refers to an 
    Intergeneric hybrid or an Intergeneric graft chimaera.
    Content of genhyb   Nature of Name in gen
    H        An intergeneric hybrid collective name
    x        An Intergeneric Hybrid
    +        An Intergeneric Graft Hybrid or Graft Chimaera
    
    qualifier field designates the botanical status of the genus.
    Possible values:
    s. lat. - aggregrate family (sensu lato)
    s. str. segregate family (sensu stricto)
    '''
    
    # TODO: we should at least warn the user that a duplicate genus name is being 
    # entered
    
genus_table = Table('genus',
                    Column('id', Integer, primary_key=True),
    
                    # it is possible that there can be genera with the same name but 
                    # different authors and probably means that at different points in literature
                    # this name was used but is now a synonym even though it may not be a
                    # synonym for the same species,
                    # this screws us up b/c you can now enter duplicate genera, somehow
                    # NOTE: we should at least warn the user that a duplicate is being entered
                    #genus = StringCol(length=50)    
                    Column('genus', String(64), unique='genus_index', nullable=False),                
                    Column('hybrid', Enum(values=['H', 'x', '+', None], 
                                          empty_to_none=True), 
                                          unique='genus_index'),
                    Column('author', Unicode(255), unique='genus_index'),
                    Column('qualifier', Enum(values=['s. lat.', 's. str', None],
                                             empty_to_none=True),
                                             unique='genus_index'),
                    Column('notes', Unicode),
                    #family = ForeignKey('Family', notNull=True, cascade=False)                    
                    Column('family_id', Integer, ForeignKey('family.id'), 
                           nullable=False, unique='genus_index'))
    
class Genus(bauble.BaubleMapper):
        
    def __str__(self):
        if self.hybrid:
            return '%s %s' % (self.hybrid, self.genus)
        else:
            return self.genus
    
    @staticmethod
    def str(genus, full_string=False):
        # TODO: should the qualifier be a standard part of the string, is it
        # standard as part of botanical nomenclature
        if full_string and genus.qualifier is not None:
            return '%s (%s)' % (str(genus), genus.qualifier)
        else:
            return str(genus)
        
genus_synonym_table = Table('genus_synonym',
                            Column('id', Integer, primary_key=True),
                            Column('genus_id', Integer, ForeignKey('genus.id'), 
                                   nullable=False),
                            Column('synonym_id', Integer, 
                                   ForeignKey('genus.id'), nullable=False))

class GenusSynonym(bauble.BaubleMapper):
        
    def __str__(self):        
        return '(%s)' % self.synonym

from bauble.plugins.plants.family import Family
from bauble.plugins.plants.species_model import Species
from bauble.plugins.plants.species_editor import SpeciesEditor

mapper(Genus, genus_table,
       properties = {'species': relation(Species, backref=backref('genus', lazy=False),
                                         order_by=['sp', 'infrasp_rank', 'infrasp']),
                     'synonyms': relation(GenusSynonym, backref='genus',
                                          primaryjoin=genus_synonym_table.c.genus_id==genus_table.c.id,
                                          order_by=['sp', 'infrasp_rank', 'infrasp'])},
       order_by=['genus', 'author'])

mapper(GenusSynonym, genus_synonym_table)
            
    
class GenusEditorView(GenericEditorView):
    
    syn_expanded_pref = 'editor.genus.synonyms.expanded'

    def __init__(self, parent=None):
        GenericEditorView.__init__(self, os.path.join(paths.lib_dir(), 
                                                      'plugins', 'plants', 
                                                      'editors.glade'),
                                   parent=parent)
        self.widgets.genus_dialog.set_transient_for(parent)
        self.connect_dialog_close(self.widgets.genus_dialog)
        self.attach_completion('gen_family_entry')

        
    def save_state(self):
        prefs[self.syn_expanded_pref] = \
            self.widgets.gen_syn_expander.get_expanded()    

        
    def restore_state(self):
        expanded = prefs.get(self.syn_expanded_pref, True)
        self.widgets.gen_syn_expander.set_expanded(expanded)

            
    def start(self):
        return self.widgets.genus_dialog.run()    
        

class GenusEditorPresenter(GenericEditorPresenter):
    
    widget_to_field_map = {'gen_family_entry': 'family_id',
                           'gen_genus_entry': 'genus',
                           'gen_author_entry': 'author',
                           'gen_hybrid_combo': 'hybrid',
#                           'gen_qualifier_combo': 'qualifier'
                           'gen_notes_textview': 'notes'}

    
    def __init__(self, model, view):
        '''
        @model: should be an instance of class Genus
        @view: should be an instance of GenusEditorView
        '''
        GenericEditorPresenter.__init__(self, ModelDecorator(model), view)
        self.session = object_session(model)
        
        # initialize widgets
        self.init_enum_combo('gen_hybrid_combo', 'hybrid')
        
        self.refresh_view() # put model values in view
        
        # connect signals
        def fam_get_completions(text):            
            return self.session.query(Family).select(Family.c.family.like('%s%%' % text))
        def set_in_model(self, field, value):
            setattr(self.model, field, value.id)
        self.assign_completions_handler('gen_family_entry', 'family_id', 
                                        fam_get_completions, set_func=set_in_model)        
        self.assign_simple_handler('gen_genus_entry', 'genus')
        self.assign_simple_handler('gen_hybrid_combo', 'hybrid')
        self.assign_simple_handler('gen_author_entry', 'author')
        #self.assign_simple_handler('gen_qualifier_combo', 'qualifier')
        self.assign_simple_handler('gen_notes_textview', 'notes')
        
        
    def refresh_view(self):
        for widget, field in self.widget_to_field_map.iteritems():
            # TODO: it would be nice to have a generic way to accession the 
            # foreign table from the foreign key
#            if field.endswith('_id') and self.model.c[field].foreign_key is not None:                
#                value = self.model[]
            if field == 'family_id':
                value = self.model.family
            else:
                value = self.model[field]
            self.view.set_widget_value(widget, value)        

    
    def start(self):
        return self.view.start()
    
    
class GenusEditor(GenericModelViewPresenterEditor):
    
    label = 'Genus'
    
    # these have to correspond to the response values in the view
    RESPONSE_OK_AND_ADD = 11
    RESPONSE_NEXT = 22
    ok_responses = (RESPONSE_OK_AND_ADD, RESPONSE_NEXT)    
        
        
    def __init__(self, model_or_defaults=None, parent=None):
        '''
        @param model_or_defaults: Genus instance or default values
        @param parent: None
        '''        
        if isinstance(model_or_defaults, dict):
            model = Genus(**model_or_defaults)
        elif model_or_defaults is None:
            model = Genus()
        elif isinstance(model_or_defaults, Genus):
            model = model_or_defaults
        else:
            raise ValueError('model_or_defaults argument must either be a '\
                             'dictionary or Genus instance')
        GenericModelViewPresenterEditor.__init__(self, model, parent)
        if parent is None: # should we even allow a change in parent
            parent = bauble.app.gui.window
        self.parent = parent
        
    
    _committed = [] # TODO: shouldn't be class level
    
    def handle_response(self, response):
        '''
        handle the response from self.presenter.start() in self.start()
        '''
        not_ok_msg = 'Are you sure you want to lose your changes?'
        if response == gtk.RESPONSE_OK or response in self.ok_responses:
            try:
                self.commit_changes()
                self._committed = [self.model]
            except SQLError, e:                
                msg = 'Error committing changes.\n\n%s' % e.orig
                utils.message_details_dialog(msg, str(e), gtk.MESSAGE_ERROR)
                return False
            except:
                msg = 'Unknown error when committing changes. See the details '\
                      'for more information.'
                utils.message_details_dialog(msg, traceback.format_exc(), 
                                             gtk.MESSAGE_ERROR)
                return False
        elif self.session.dirty and utils.yes_no_dialog(not_ok_msg) or not self.session.dirty:
            return True
        else:
            return False
                
        # respond to responses
        more_committed = None
        if response == self.RESPONSE_NEXT:
            e = FamilyEditor(parent=self.parent)
            more_committed = e.start()
        elif response == self.RESPONSE_OK_AND_ADD:
            e = SpeciesEditor(parent=self.parent, 
                            model_or_defaults={'genus_id': self._committed[0].id})
            more_committed = e.start()
             
        if more_committed is not None:
            if isinstance(more_committed, list):
                self._committed.extend(more_committed)
            else:
                self._committed.append(more_committed)                
        
        return True                

    
    def start(self):
        if self.session.query(Family).count() == 0:        
            msg = 'You must first add or import at least one Family into the '\
                  'database before you can add plants.'
            utils.message_dialog(msg)
            return
        self.view = GenusEditorView(parent=self.parent)
        self.presenter = GenusEditorPresenter(self.model, self.view)
        
        exc_msg = "Could not commit changes.\n"
        committed = None
        while True:
            response = self.presenter.start()
            self.view.save_state() # should view or presenter save state
            if self.handle_response(response):
                break
            
        self.session.close() # cleanup session
        return self._committed
        
    #class Genus(BaubleTable):
    #
    #    class sqlmeta(BaubleTable.sqlmeta):
    #        defaultOrder = 'genus'
    #    
    #    # it is possible that there can be genera with the same name but 
    #    # different authors and probably means that at different points in literature
    #    # this name was used but is now a synonym even though it may not be a
    #    # synonym for the same species,
    #    # this screws us up b/c you can now enter duplicate genera, somehow
    #    # NOTE: we should at least warn the user that a duplicate is being entered
    #    genus = StringCol(length=50)    
    #            
    #    '''
    #    hybrid: indicates whether the name in the Genus Name field refers to an 
    #    Intergeneric hybrid or an Intergeneric graft chimaera.
    #    Content of genhyb   Nature of Name in gen
    #     H        An intergeneric hybrid collective name
    #     x        An Intergeneric Hybrid
    #     +        An Intergeneric Graft Hybrid or Graft Chimaera
    #    '''
    #    hybrid = EnumCol(enumValues=("H", "x", "+", None), default=None) 
    #    '''    
    #    The qualifier field designates the botanical status of the genus.
    #    Possible values:
    #        s. lat. - aggregrate family (sensu lato)
    #        s. str. segregate family (sensu stricto)
    #    '''
    #    qualifier = EnumCol(enumValues=('s. lat.', 's. str.', None), default=None)
    #    author = UnicodeCol(length=255, default=None)
    #    notes = UnicodeCol(default=None)
    #    
    #    # indices
    #    # we can't do this right now unless we do more work on 
    #    # the synonyms table, see 
    #    # {'author': 'Raf.', 'synonymID': 13361, 'familyID': 214, 'genus': 'Trisiola', 'id': 15845}
    #    # in Genus.txt
    #    genus_index = DatabaseIndex('genus', 'author', 'family', unique=True)
    #    
    #    # foreign keys
    #    family = ForeignKey('Family', notNull=True, cascade=False)
    #    
    #    # joins
    #    species = MultipleJoin("Species", joinColumn="genus_id")
    #    synonyms = MultipleJoin('GenusSynonym', joinColumn='genus_id')    
    #
    #
    #    def __str__(self):
    #        if self.hybrid:
    #            return '%s %s' % (self.hybrid, self.genus)
    #        else:
    #            return self.genus
    #    
    #    @staticmethod
    #    def str(genus, full_string=False):
    #        # TODO: should the qualifier be a standard part of the string, is it
    #        # standard as part of botanical nomenclature
    #        if full_string and genus.qualifier is not None:
    #            return '%s (%s)' % (str(genus), genus.qualifier)
    #        else:
    #            return str(genus)
    
            
    #class GenusSynonym(BaubleTable):
    #    
    #    # deleting either of the genera this synonym refers to makes this 
    #    # synonym irrelevant
    #    genus = ForeignKey('Genus', default=None, cascade=True)
    #    synonym = ForeignKey('Genus', cascade=True)
    #    
    #    def __str__(self):
    #        return self. synonym
    #
    #    def markup(self):
    #        return '%s (syn. of %f)' % (self.synonym, self.genus)
    
        
#
# infobox
#
try:
    from bauble.plugins.searchview.infobox import InfoBox, InfoExpander
except ImportError:
    pass
else:    
    from sqlalchemy.orm.session import object_session
    import bauble.paths as paths
    from bauble.plugins.plants.species_model import Species, species_table
    from bauble.plugins.garden.accession import Accession
    from bauble.plugins.garden.plant import Plant
    
    class GeneralGenusExpander(InfoExpander):
        '''
        expander to present general information about a genus
        '''
    
        def __init__(self, widgets):
            '''
            the constructor
            '''
            InfoExpander.__init__(self, "General", widgets)
            general_box = self.widgets.gen_general_box
            self.widgets.remove_parent(general_box)
            self.vbox.pack_start(general_box)
            
            
        def update(self, row):
            '''
            update the expander
            
            @param row: the row to get the values from
            '''
            self.set_widget_value('gen_name_data', str(row))
            session = object_session(row)
            
            species_query = session.query(Species)            
            species = species_query.table            
            nsp = species_query.count_by(genus_id = row.id)
            self.set_widget_value('gen_nsp_data', nsp)
            
            def get_unique_in_select(sel, col):
                return select([sel.c[col]], distinct=True).count().scalar()
            
            acc_query = session.query(Accession)
            accession = acc_query.table                     
            sp = select([species.c.id], species.c.genus_id==row.id)
            acc = accession.select(accession.c.species_id.in_(sp))     
            nacc = acc.count().scalar()
            nacc_str = str(nacc)
            if nacc > 0:
                nsp_with_accessions = get_unique_in_select(acc, 'species_id')
                nacc_str = '%s in %s species' % (nacc_str, nsp_with_accessions)
            
            plant_query = session.query(Plant)
            plant = plant_query.table
            acc_ids = select([acc.c.id])
            plants = plant.select(plant.c.accession_id.in_(acc_ids))
            nplants = plants.count().scalar()
            nplants_str = str(nplants)
            if nplants > 0:
                nacc_with_plants = get_unique_in_select(plants, 'accession_id')
                nplants_str = '%s in %s accessions' % (nplants_str, nacc_with_plants)                        
                
            self.set_widget_value('gen_nacc_data', nacc_str)
            self.set_widget_value('gen_nplants_data', nplants_str)
                
                
    class GenusInfoBox(InfoBox):
        """
        - number of taxon in number of accessions
        - references
        """
        def __init__(self):
            InfoBox.__init__(self)
            glade_file = os.path.join(paths.lib_dir(), 'plugins', 'plants', 
                                      'infoboxes.glade')            
            self.widgets = utils.GladeWidgets(gtk.glade.XML(glade_file))
            self.general = GeneralGenusExpander(self.widgets)
            self.add_expander(self.general)
        
        def update(self, row):
            self.general.update(row)
