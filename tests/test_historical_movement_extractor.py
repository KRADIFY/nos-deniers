"""Regression cases for independent historical movement PDF extraction."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
import fitz

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('historical_extractor',ROOT/'tools/extract_historical_detail.py')
extractor=importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)

class HistoricalMovementExtractorTests(unittest.TestCase):
    def test_full_titles_apostrophes_and_advances_are_distinct(self):
        cases={
            "ARRÊTÉS DE RATTACHEMENT D'ATTRIBUTIONS DE PRODUITS":'RATTACHEMENT_ADP',
            "OUVERTURES PAR VOIE D'ATTRIBUTION DE PRODUITS":'RATTACHEMENT_ADP',
            'OUVERTURES PAR VOIE DE FONDS DE CONCOURS':'RATTACHEMENT_FDC',
            'ARRÊTÉS DE REPORT DE CRÉDITS OUVERTS PAR VOIE DE FONDS DE CONCOURS':'REPORT_FDC',
            'ARRÊTÉS DE REPORT DE CRÉDITS HORS FONDS DE CONCOURS':'REPORT_GENERAL',
            "ARRÊTÉS DE REPORT D'AENE":'REPORT_AENE',
            "DÉCRETS D'ANNULATION DE FDC OU DE ADP":'ANNULATION_FDC_ADP',
            "DÉCRETS D'AVANCE":'DECRET_AVANCE',
            'DÉCRETS DE DÉPENSES ACCIDENTELLES':'DEPENSES_ACCIDENTELLES',
        }
        for caption,kind in cases.items():
            with self.subTest(caption=caption):self.assertEqual(extractor.kind_of(caption)[0],kind)

    @staticmethod
    def text(page,x,y,text):page.insert_text((x,y),text,fontsize=8)

    def headers(self,page,y):
        self.text(page,120,y,'Ouvertures');self.text(page,350,y,'Annulations')
        for j in range(8):self.text(page,120+j*54,y+20,'Titre 2' if j%2==0 else 'Autres titres')

    def amount(self,page,y,label,value):
        self.text(page,40,y,label);self.text(page,174,y,str(value));self.text(page,282,y,str(value))

    def test_continuation_uses_its_real_total_and_keeps_source_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.pdf';doc=fitz.open()
            first=doc.new_page();self.text(first,40,20,'RECAPITULATION DES MOUVEMENTS DE CREDITS')
            self.text(first,40,45,'ARRETES DE RATTACHEMENT DE FDC');self.headers(first,60)
            self.amount(first,105,'01/2019',10)
            second=doc.new_page();self.headers(second,60);self.amount(second,105,'02/2019',20)
            self.amount(second,130,'Total',30)
            self.text(second,40,165,'TOTAL DES OUVERTURES ET ANNULATIONS');self.headers(second,180)
            self.amount(second,225,'Total general',30);doc.save(path);doc.close()
            rows,totals,problems,inspection=extractor.parse_document(path,2019,'TA','174','a'*20,'b'*64)
        self.assertEqual(problems,[])
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['table_id'],rows[1]['table_id'])
        self.assertEqual([r['page'] for r in rows],[1,2]);self.assertTrue(rows[1]['continuation'])
        self.assertEqual(len(totals),2)
        self.assertTrue(all(t['read_independently_from_source'] for t in totals))
        self.assertTrue(all(c['difference_cents']==0 for t in totals for c in t['checks']))
        self.assertEqual(totals[-1]['cells'][1]['raw_text'],'30')
        self.assertIn('bbox',totals[-1]['cells'][1])
        # A source total is not replaced by the row sum when it disagrees.
        totals[-1]['cells'][1]['amount_cents']=5000
        check=extractor.checks_for(totals[-1],rows)[1]
        self.assertEqual(check['difference_cents'],2000);self.assertFalse(check['accepted'])

    def test_missing_canonical_zero_requires_an_explicit_current_year_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.pdf';doc=fitz.open();page=doc.new_page()
            self.text(page,40,25,'Prevision LFI 2020')
            self.text(page,40,55,'Total des AE prevues en LFI');self.text(page,300,55,'0')
            self.text(page,40,80,'Total des CP prevus en LFI')
            self.text(page,40,105,'Total des AE ouvertes');self.text(page,300,105,'30')
            doc.save(path);doc.close()
            source={'id':'a'*20,'sha256':'b'*64}
            refs,proofs=extractor.recover_missing_reference(path,2020,'174',{},source)
            wrong_year,_=extractor.recover_missing_reference(path,2019,'174',{},source)
        self.assertEqual(refs[('LFI','AE')],0)
        self.assertEqual(refs[('OUVERT','AE')],3000)
        self.assertNotIn(('LFI','CP'),refs)
        self.assertEqual(wrong_year,{})
        self.assertTrue(all(p['canonical_fact_missing'] for p in proofs))

    def test_unrecognized_caption_is_not_classified_as_a_previous_table(self):
        self.assertIsNone(extractor.kind_of('ARRETES DE MOUVEMENTS INCONNUS'))

if __name__=='__main__':unittest.main()
