"""Integrazioni esterne — Sprint 7.10 MR α.5+.

Client per servizi esterni dell'ecosistema ARTURO (live.arturo.travel,
travel.arturo, ecc.). Ogni client deve essere robusto: timeout
configurati, fallback a comportamento safe (= "non ho trovato nulla")
in caso di errore di rete o API down. Mai propagare un'eccezione di
rete in modo che blocchi il flusso principale del builder.
"""
