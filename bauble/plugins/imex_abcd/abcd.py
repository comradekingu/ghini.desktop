#
# abcd.py
# 
# module for read and writing Access to Biological Collection 
# Data (ABCD) files
#

import string
from string import Template
from bauble.utils.log import log, debug
import xml.sax.saxutils
import lxml.etree as etree
from lxml.etree import Element, SubElement, ElementTree

# TODO: also need ability to dump to darwin core, should consider just writing
# an xsl transformation to do the conversion instead of writing more export
# code, Darwin Core is a flat structure and from i understand doesn't have a 
# sense of "unit"

# TODO: need to also respect the number of children and element can have
# e.g. Units can have 1 to infinity Unit children whereas elements require
# at least one and some can have at most one child

# TODO: the code needs to reflect the fact that xml tags are case insensitive,
# at the very least the parent.tag assertion should call a lower

# TODO: for types that are enumerations only allow values from the 
# enumeration in the text attribute

# TODO: doesn't validate unless i write the dataset to a file and read it back 
# in, it's most like some sort of namespace issue

def ABCDElement(parent, name, type=None, text=None, attrib={}):
    el = SubElement(parent, name, attrib)
    el.text = text
    return el
    
def DataSets():
    #return Element('{http://www.tdwg.org/schemas/abcd/2.06}DataSets')
    return Element('DataSets', attrib={'xmlns': 'http://www.tdwg.org/schemas/abcd/2.06'})
    


#
# using a factory means less typos but also less flexibility
#
# {tagname: parents}
element_map = {'DataSet': ['{http://www.tdwg.org/schemas/abcd/2.06}DataSets', 'DataSets'],
                   'TechnicalContacts': ['DataSet'],
                       'TechnicalContact': ['TechnicalContacts'],
                   'ContentContacts': ['DataSet'],
                       'ContentContact': ['ContentContacts'],
                   'Name': ['TechnicalContact','ContentContact'],
                   'Email': ['TechnicalContact','ContentContact'],
               'Metadata': ['DataSet'],
                   'Description': ['Metadata'],
                   'Representation': ['Description'], # language attribute
                       'Title': ['Representation'],
                   'RevisionData': ['Metadata'],
                       'DateModified': ['RevisionData'],                   
               'Units': ['DataSet'],
                   'Unit': ['Units'],
                       'SourceInstitutionID': ['Unit'],
                       'SourceID': ['Unit'],
                       'UnitID': ['Unit'],
                       'DateLastEdited': ['Unit'],                       
                       'Identifications': ['Unit'],
                           'Identification': ['Identifications'],
                               'Result': ['Identification'],
                                   'TaxonIdentified': ['Result'],
                                       'HigherTaxa': ['TaxonIdentified'],
                                       'HigherTaxon': ['HigherTaxa'],
                                           'HigherTaxonName': ['HigherTaxon'],
                                           'HigherTaxonRank': ['HigherTaxon'],
                                   'ScientificName': ['TaxonIdentified'],
                                       'FullScientificNameString': ['ScientificName'],
                                       'NameAtomised': ['ScientificName'],
                                           'Botanical': ['NameAtomised'],
                                               'GenusOrMonomial': ['Botanical'],
                                               'FirstEpithet': ['Botanical'],
                                               'AuthorTeam': ['Botanical'],
                                   
                           }

def ElementFactory(parent, name, **kwargs):
    assert name in element_map, 'Unknown element: %s' % name
    assert parent.tag in element_map[name], parent.tag
    el = ABCDElement(parent, name, **kwargs)
    return el


main_template_str = """<?xml version="1.0" encoding="utf-8"?>
<datasets xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:noNamespaceSchemaLocation="file:/home/brett/devel/ABCD/ABCD.xsd">
    <dataset>
        <units>
            $units
        </units>
    </dataset>
</datasets>
"""
main_template = Template(main_template_str)

unit_template_str = """
           <unit>
                <unitid>$unitid</unitid>
                <identifications>
                    <identification>
                    <result>
                        <taxonidentified>
                           <scientificname>
                             $family
                             $scientific_name
                             $informal_names
                             $distribution
                           </scientificname>
                         </taxonidentified>
                    </result>
                 </identification>
                </identifications>
            </unit>
"""
unit_template = Template(unit_template_str)


family_template_str = """
<highertaxa>
    <highertaxon>
        <highertaxonrank>familia</highertaxonrank>
        <highertaxonname>$family</highertaxonname>
     </highertaxon>                                    
</highertaxa>
"""
family_template = Template(family_template_str)


name_template_str = """
<scientificname>
  <fullscientificnamestring>
    $name
  </fullscientificnamestring>
</scientificname>
"""
name_template = Template(name_template_str)


# ***********
# TODO: this is not a standard in ABCD but we need it to create the labels
# if we could just return this abcd data instead of writing a file then 
# we could add
distribution_template_str = """
<distribution>
$distribution
</distribution>
"""
distribution_template = Template(distribution_template_str)


#
# i'm using informal name here for the vernacular name
#
informal_name_str = """
<informalnamestring>
$informal_name
</informalnamestring>
"""
informal_name_template = Template(informal_name_str)




def accessions_to_abcd(accessions):
    """
    convert a list of accessions instance to an abcd record
    """
    plants = []
    # get a list of all plants and pass to plants_to_abcd
    for a in accessions:
        for p in a.plants:
            plants.append(p)
    return plants_to_abcd(plants)
    
def xml_safe(ustr):    
    return xml.sax.saxutils.escape(ustr).encode('utf-8')


def plants_to_abcd(plants):
    """
    convert a list of plants/clones instances to an abcd record
    """
    abcd = None
    units = []
    for p in plants:
        acc = p.accession
        #id = string.strip(unicode(acc.acc_id) + '.' + str(p.plant_id))
        # TODO: what if someone doesn't want to use '.' to separate 
        # acc_id and plant_id
        id = xml_safe(acc.code + '.' + p.code)
        
        f = family_template.substitute(family=xml_safe(str(acc.species.genus.family)))
        n = name_template.substitute(name=xml_safe(str(acc.species)))
        v = acc.species.default_vernacular_name or ""
        informal_name = informal_name_template.substitute(informal_name=
                                                          xml_safe(str(v)))
        
        if acc.species.species_meta:
            d = acc.species.species_meta.distribution or ""
        else:
            d = ""
        dist = distribution_template.substitute(distribution=xml_safe(str(d)))
        
        units.append(unit_template.substitute(unitid=id, family=f, 
                                              scientific_name=n, 
                                              informal_names=informal_name,
                                              distribution=dist))
    
    #abcd = xml.sax.saxutils.escape(main_template.substitute(units='\n'.join(units))).encode('utf-8')
    abcd = main_template.substitute(units='\n'.join(units))
    #debug(abcd)
    return abcd
