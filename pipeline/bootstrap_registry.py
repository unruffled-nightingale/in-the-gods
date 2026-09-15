"""
!! ONE-TIME BOOTSTRAP — DO NOT RE-RUN !!

This generated the first data/venues.yaml from the research docs.
Since then venues.yaml has been hand-edited (trailing_slash flags,
per-venue notes, verified URLs) and those edits are NOT reproduced
here. Re-running this overwrites them silently.

venues.yaml is the source of truth now. This file is provenance only.
"""

#!/usr/bin/env python3
"""
make_registry.py — generate the full venues.yaml from the researched venue list.

Design decision worth understanding:

  Identity fields (name, description, location, tags, tier) are RESEARCHED —
  they come from the comprehensive list and are stable.

  Technical fields (whats_on_url, fetch_method, one_stage, selectors) are
  UNVERIFIED for every venue except the five already probed. Rather than
  guessing URLs and shipping a registry full of 404s, unverified venues get:
      whats_on_url: null
      url_candidates: [list of paths to try]
      fetch_method: unverified
  probe.py walks the candidates, finds the one that returns listings, and
  writes back the confirmed values.

So this file is complete on the half a human had to research, and honestly
blank on the half a script should determine.
"""

import yaml
from pathlib import Path

# Common listings paths, tried in order by probe.py
CANDIDATES = ["/whats-on/", "/whats-on", "/whatson", "/productions/",
              "/events/", "/programme/", "/"]

# id, name, domain, tier, compass, area, borough, station, tags, description
V = [
 # ---------- TIER 1: flagship producing houses ----------
 ("almeida","Almeida Theatre","almeida.co.uk",1,"North","Islington","Islington","Angel",
  ["text"],"Reimagined classics and new work, stunningly designed, regularly transferring."),
 ("young-vic","Young Vic","youngvic.org",1,"South","South Bank","Lambeth","Waterloo",
  ["text","devised"],"Directors' theatre. Bold reinventions and international work across three spaces."),
 ("donmar","Donmar Warehouse","donmarwarehouse.com",1,"Central","Covent Garden","Westminster","Covent Garden",
  ["text"],"251 seats. New writing, European classics, small-scale musicals."),
 ("royal-court","Royal Court","royalcourttheatre.com",1,"West","Sloane Square","Kensington & Chelsea","Sloane Square",
  ["text"],"Home of new writing since 1956. Jerwood Downstairs (380) and Upstairs (85)."),
 ("bush","Bush Theatre","bushtheatre.co.uk",1,"West","Shepherd's Bush","Hammersmith & Fulham","Shepherd's Bush",
  ["text"],"New writers in the former Shepherd's Bush Library."),
 ("hampstead","Hampstead Theatre","hampsteadtheatre.com",1,"North","Swiss Cottage","Camden","Swiss Cottage",
  ["text"],"Main stage plus Downstairs studio. Premieres; Pinter premiered here."),
 ("kiln","Kiln Theatre","kilntheatre.com",1,"North-West","Kilburn","Brent","Kilburn",
  ["text"],"Diverse producing house, formerly the Tricycle."),
 ("lyric-hammersmith","Lyric Hammersmith","lyric.co.uk",1,"West","Hammersmith","Hammersmith & Fulham","Hammersmith",
  ["text"],"Frank Matcham auditorium plus studio. Ambitious plays and musicals."),
 ("orange-tree","Orange Tree","orangetreetheatre.co.uk",1,"South-West","Richmond","Richmond","Richmond",
  ["text"],"Theatre-in-the-round. Rediscovered classics and new writing."),
 ("soho-theatre","Soho Theatre","sohotheatre.com",1,"Central","Soho","Westminster","Tottenham Court Road",
  ["text","music-hall"],"New comedy, cabaret and new writing. Hub for edgy solo work."),
 ("park-theatre","Park Theatre","parktheatre.co.uk",1,"North","Finsbury Park","Islington","Finsbury Park",
  ["text"],"Park200 and Park90. Polished plays and revivals."),
 ("hackney-empire","Hackney Empire","hackneyempire.co.uk",1,"East","Hackney","Hackney","Hackney Central",
  ["music-hall"],"Grand Matcham variety house. Panto, comedy, music, touring drama."),
 ("stratford-east","Theatre Royal Stratford East","stratfordeast.com",1,"East","Stratford","Newham","Stratford",
  ["text"],"Historic radical producing house. New musicals, diverse new writing."),
 ("coronet","The Coronet Theatre","thecoronettheatre.com",1,"West","Notting Hill","Kensington & Chelsea","Notting Hill Gate",
  ["text","physical","live-art"],"Atmospheric former cinema. European-leaning theatre, dance, music and art in a beautifully faded auditorium."),
 ("menier","Menier Chocolate Factory","menierchocolatefactory.com",1,"South","Southwark","Southwark","London Bridge",
  ["text"],"Studio plus restaurant. Acclaimed musical revivals."),
 ("barbican","Barbican Centre","barbican.org.uk",1,"Central","Barbican","City of London","Barbican",
  ["physical","devised","immersive"],"Brutalist labyrinth. Barbican Theatre and The Pit host international and formally ambitious work — Complicite, Lepage, Punchdrunk collaborations."),
 ("national-theatre","National Theatre","nationaltheatre.org.uk",1,"South","South Bank","Lambeth","Waterloo",
  ["text"],"Olivier, Lyttelton, Dorfman. The Dorfman is where the odd work lands."),

 # ---------- TIER 1: experimental / live art / craft ----------
 ("bac","Battersea Arts Centre","bac.org.uk",1,"South","Battersea","Wandsworth","Clapham Junction",
  ["devised","live-art","immersive"],"Old Town Hall. Pioneered the Scratch model; one-on-one and building-wide work."),
 ("the-yard","The Yard Theatre","theyardtheatre.co.uk",1,"East","Hackney Wick","Hackney","Hackney Wick",
  ["devised","live-art","text"],"Converted warehouse. Formally strange new work and club nights."),
 ("camden-peoples-theatre","Camden People's Theatre","cptheatre.co.uk",1,"North","Euston","Camden","Warren Street",
  ["devised","live-art","physical"],"Scruffy 60-seater for experimental, feminist, queer and physical performance."),
 ("artsadmin","Artsadmin / Toynbee Studios","artsadmin.co.uk",1,"East","Aldgate","Tower Hamlets","Aldgate East",
  ["live-art","devised"],"280-seat art-deco theatre plus studios. Live art and interdisciplinary work."),
 ("chisenhale-dance","Chisenhale Dance Space","chisenhaledancespace.co.uk",1,"East","Bow","Tower Hamlets","Mile End",
  ["live-art","physical"],"Artist member-led since 1984, atop a former veneer factory. Raw and process-driven."),
 ("shoreditch-town-hall","Shoreditch Town Hall","shoreditchtownhall.com",1,"East","Shoreditch","Hackney","Old Street",
  ["immersive","devised"],"Victorian civic building; the basements host site-responsive and immersive work."),
 ("new-diorama","New Diorama Theatre","newdiorama.com",1,"North","Regent's Place","Camden","Great Portland Street",
  ["devised","physical"],"80 seats, two Peter Brook awards. Ensemble and devised companies."),
 ("rich-mix","Rich Mix","richmix.org.uk",1,"East","Shoreditch","Tower Hamlets","Shoreditch High Street",
  ["live-art","physical"],"Converted leather factory. Cross-arts: theatre, dance, spoken word, film."),
 ("wiltons","Wilton's Music Hall","wiltons.org.uk",1,"East","Shadwell","Tower Hamlets","Tower Hill",
  ["music-hall","spooky","physical","opera"],"World's oldest surviving grand music hall. Opera, puppetry, cabaret, magic, silent film with live score."),
 ("hoxton-hall","Hoxton Hall","hoxtonhall.co.uk",1,"East","Hoxton","Hackney","Hoxton",
  ["music-hall"],"Rare surviving Victorian saloon-style music hall."),
 ("jacksons-lane","Jacksons Lane","jacksonslane.org.uk",1,"North","Highgate","Haringey","Highgate",
  ["circus","physical"],"UK's leading contemporary circus venue, in a Grade II Edwardian Methodist church."),
 ("punchdrunk","Punchdrunk","punchdrunk.com",1,"South-East","Woolwich","Greenwich","Woolwich",
  ["immersive"],"Permanent Woolwich home. Vast, hyper-detailed masked worlds."),
 ("woolwich-works","Woolwich Works","woolwich.works",1,"South-East","Woolwich","Greenwich","Woolwich",
  ["circus","physical","music-hall"],"Royal Arsenal creative district. Concerts, circus, performance."),
 ("sadlers-wells","Sadler's Wells","sadlerswells.com",1,"Central","Angel","Islington","Angel",
  ["physical","circus"],"Dance house; also the main MimeLondon partner venue."),
 ("the-place","The Place","theplace.org.uk",1,"Central","Euston","Camden","Euston",
  ["physical"],"Contemporary dance and experimental movement work."),
 ("ica","ICA","ica.art",1,"Central","The Mall","Westminster","Charing Cross",
  ["live-art","devised"],"Live art, performance and screenings alongside the gallery programme."),

 # ---------- TIER 1: puppetry ----------
 ("little-angel","Little Angel Theatre","littleangeltheatre.com",1,"North","Islington","Islington","Angel",
  ["puppetry"],"Home of British puppetry since 1961. Former temperance hall, 100 seats, plus a studio on Sebbon Street. Mostly children's work — watch visiting companies and the heritage strand."),
 ("puppet-barge","Puppet Theatre Barge","puppetbarge.com",1,"West","Little Venice","Westminster","Warwick Avenue",
  ["puppetry"],"50-seat marionette theatre on a converted Thames barge. Little Venice Oct–Jul, Richmond in summer."),

 # ---------- TIER 1: South London producing houses ----------
 ("brixton-house","Brixton House","brixtonhouse.co.uk",1,"South","Brixton","Lambeth","Brixton",
  ["text","devised"],"Successor to Ovalhouse. Two auditoria, socially engaged and community-rooted."),
 ("omnibus","Omnibus Theatre","omnibus-clapham.org",1,"South","Clapham","Lambeth","Clapham Common",
  ["text","devised"],"Clapham's old Victorian library. Reimagined classics; the queer 96 Festival."),
 ("the-albany","The Albany","thealbany.org.uk",1,"South-East","Deptford","Lewisham","Deptford",
  ["devised","live-art"],"Multi-arts centre; hosted Sun & Sea for LIFT. Music, spoken word, theatre."),
 ("greenwich-theatre","Greenwich Theatre","greenwichtheatre.org.uk",1,"South-East","Greenwich","Greenwich","Cutty Sark",
  ["text"],"Former Victorian music hall. Drama, panto, studio work; a GDIF partner."),
 ("tara-theatre","Tara Theatre","taratheatre.com",1,"South-West","Earlsfield","Wandsworth","Earlsfield",
  ["text"],"100-seat producing house. Pioneering South Asian and global-majority company since 1977."),
 ("streatham-space","Streatham Space Project","streathamspaceproject.co.uk",1,"South","Streatham Hill","Lambeth","Streatham Hill",
  ["text","devised"],"Purpose-built 120-seat neighbourhood venue. Theatre, comedy, music, mini-festivals."),
 ("clf-art-cafe","CLF Art Café (Bussey Building)","clfartcafe.org",1,"South-East","Peckham","Southwark","Peckham Rye",
  ["live-art","devised"],"Former cricket-bat factory. Theatre, opera, film and raves in a raw warehouse."),
 ("southwark-playhouse","Southwark Playhouse","southwarkplayhouse.co.uk",1,"South","Borough","Southwark","Elephant & Castle",
  ["text","spooky"],"Two buildings, three spaces. Borough (The Little / The Large) is the scrappier, more interesting one."),
 ("theatre-peckham","Theatre Peckham","theatrepeckham.co.uk",1,"South-East","Peckham","Southwark","Peckham Rye",
  ["text"],"Producing house and training ground for young South-East London talent."),

 # ---------- TIER 1: other mid-scale ----------
 ("arcola","Arcola Theatre","arcolatheatre.com",1,"East","Dalston","Hackney","Dalston Junction",
  ["opera","text","spooky"],"Former paint factory, two studios. Pay-What-You-Can Tuesdays and the Grimeborn opera festival."),
 ("gate-theatre","Gate Theatre","gatetheatre.co.uk",1,"North","itinerant","—","varies",
  ["text","devised"],"International/experimental company, itinerant since leaving Notting Hill in 2022. Track by production."),
 ("marylebone-theatre","Marylebone Theatre","marylebonetheatre.com",1,"Central","Marylebone","Westminster","Baker Street",
  ["text"],"Newer producing house. Ambitious plays and premieres."),
 ("riverside-studios","Riverside Studios","riversidestudios.co.uk",1,"West","Hammersmith","Hammersmith & Fulham","Hammersmith",
  ["text","physical"],"Riverside arts complex. Theatre, dance and international work."),
 ("the-cockpit","The Cockpit","thecockpit.org.uk",1,"Central","Marylebone","Westminster","Edgware Road",
  ["devised","music-hall"],"London's oldest purpose-built theatre-in-the-round. Birthplace of the Mime Festival."),
 ("artsdepot","artsdepot","artsdepot.co.uk",1,"North","North Finchley","Barnet","Woodside Park",
  ["text","physical"],"395-seat Pentland Theatre plus studio. Theatre, dance, comedy."),
 ("bernie-grant","Bernie Grant Arts Centre","berniegrantcentre.co.uk",1,"North","Tottenham","Haringey","Seven Sisters",
  ["text","live-art"],"Adjaye-designed multi-arts centre focused on culturally diverse and Black artists."),
 ("chickenshed","Chickenshed","chickenshed.org.uk",1,"North","Southgate","Enfield","Oakwood",
  ["devised"],"Inclusive theatre company since 1974 in a purpose-built complex."),
 ("alexandra-palace","Alexandra Palace Theatre","alexandrapalace.com",1,"North","Wood Green","Haringey","Alexandra Palace",
  ["spooky","music-hall"],"Restored Victorian theatre with distressed-plaster charm. Home of Gatiss's annual Christmas ghost story."),
 ("wac-arts","Wac Arts","wacarts.co.uk",1,"North","Belsize Park","Camden","Belsize Park",
  ["devised"],"Old Hampstead Town Hall. Youth and community-led performance."),

 # ---------- TIER 2: North / North-East fringe & pub ----------
 ("kings-head","King's Head Theatre","kingsheadtheatre.com",2,"North","Islington","Islington","Angel",
  ["text","opera"],"Purpose-built 220-seat space beside the original pub theatre. Irreverent, queer-focused."),
 ("hope-theatre","The Hope Theatre","thehopetheatre.com",2,"North","Islington","Islington","Highbury & Islington",
  ["text"],"50-seat black box above the Hope & Anchor. Leadership changed in 2024 — verify current season."),
 ("old-red-lion","Old Red Lion","oldredliontheatre.co.uk",2,"North","Angel","Islington","Angel",
  ["text","spooky"],"60-seat pub theatre. New writing, revivals, and Nunkie's M.R. James ghost stories at Christmas."),
 ("hen-and-chickens","Hen & Chickens","thehenandchickenstheatrebar.co.uk",2,"North","Highbury","Islington","Highbury & Islington",
  ["text","devised"],"54-seat theatre bar. Theatre, comedy, improv, experimental new writing."),
 ("rosemary-branch","Rosemary Branch Theatre","rosemarybranchtheatre.co.uk",2,"North","De Beauvoir","Islington","Haggerston",
  ["puppetry","music-hall"],"60 seats above a Victorian pub, a former music hall. Puppetry, drag, cabaret, burlesque."),
 ("pleasance-islington","Pleasance Islington","pleasance.co.uk",2,"North","Caledonian Road","Islington","Caledonian Road",
  ["text","devised"],"London sibling of the Edinburgh Fringe venue. Comedy and emerging companies."),
 ("lion-and-unicorn","Lion & Unicorn","thelionandunicorntheatre.co.uk",2,"North","Kentish Town","Camden","Kentish Town",
  ["text"],"Pub theatre; Camden Fringe hub."),
 ("etcetera","Etcetera Theatre","etceteratheatre.com",2,"North","Camden Town","Camden","Camden Town",
  ["text","devised"],"42-seat black box above the Oxford Arms. Camden Fringe staple since 1986."),
 ("upstairs-gatehouse","Upstairs at the Gatehouse","upstairsatthegatehouse.com",2,"North","Highgate","Camden","Highgate",
  ["text"],"120 seats in a refurbished 1895 auditorium above the pub."),
 ("pentameters","Pentameters Theatre","pentameters.co.uk",2,"North","Hampstead","Camden","Hampstead",
  ["text"],"Bohemian Hampstead pub theatre since 1968. Poetry-rooted, eclectic."),
 ("well-walk","Well Walk Theatre","thewellwalktheatre.com",2,"North","Hampstead","Camden","Hampstead",
  ["puppetry","music-hall","physical"],"Tiny independent venue with a children's bookshop and café. Puppet shows, magic, silent films with live music. Theatre Building of the Year 2025."),
 ("tabernacle","The Tabernacle","tabernaclew11.com",2,"West","Notting Hill","Kensington & Chelsea","Notting Hill Gate",
  ["text","live-art"],"Grade II former church. Theatre, music and community arts."),

 # ---------- TIER 2: Central / West fringe & pub ----------
 ("finborough","Finborough Theatre","finboroughtheatre.co.uk",2,"West","Earl's Court","Kensington & Chelsea","West Brompton",
  ["text"],"Influential 50-seat pub theatre. New British writing and rediscovered 19th/20th-century plays."),
 ("jermyn-street","Jermyn Street Theatre","jermynstreettheatre.co.uk",2,"Central","St James's","Westminster","Piccadilly Circus",
  ["text","opera"],"70-seat studio off Piccadilly. Revivals, new plays, and Charles Court Opera's boutique pantos."),
 ("drayton-arms","Drayton Arms Theatre","thedraytonarmstheatre.co.uk",2,"West","South Kensington","Kensington & Chelsea","Gloucester Road",
  ["text","spooky"],"51-seat black box above a Victorian pub. Hosts the London Lovecraft Festival each February."),
 ("barons-court","Barons Court Theatre","baronscourttheatre.com",2,"West","Barons Court","Hammersmith & Fulham","Barons Court",
  ["text"],"52-seat basement under the Curtains Up. Short-run classics and afternoon magic shows."),
 ("canal-cafe","Canal Café Theatre","canalcafetheatre.com",2,"West","Little Venice","Westminster","Warwick Avenue",
  ["music-hall"],"60-seat comedy and cabaret venue. Home of NewsRevue since 1979."),
 ("tabard","Theatre at the Tabard","tabardtheatre.co.uk",2,"West","Chiswick","Hounslow","Turnham Green",
  ["text"],"Intimate pub theatre. New writing and revivals."),
 ("museum-of-comedy","Museum of Comedy","museumofcomedy.com",2,"Central","Bloomsbury","Camden","Holborn",
  ["music-hall"],"Basement venue under St George's Church. Stand-up, character comedy, offbeat nights."),
 ("underbelly-boulevard","Underbelly Boulevard","underbellyboulevard.com",2,"Central","Soho","Westminster","Piccadilly Circus",
  ["circus","music-hall"],"200-seat cabaret and variety venue on the old Boulevard Theatre site."),
 ("bridewell","Bridewell Theatre","sbf.org.uk",2,"Central","Blackfriars","City of London","Blackfriars",
  ["text"],"Former Victorian swimming pool. Amateur and small-scale professional work."),
 ("courtyard","The Courtyard Theatre","thecourtyard.org.uk",2,"East","Hoxton","Hackney","Old Street",
  ["text","devised"],"Two spaces in Hoxton. New work and emerging companies."),
 ("playground-theatre","The Playground Theatre","theplaygroundtheatre.london",2,"West","North Kensington","Kensington & Chelsea","Latimer Road",
  ["text","physical"],"Former bus depot. International and physical work; recent Gate Theatre host."),

 # ---------- TIER 2: South London fringe ----------
 ("theatre503","Theatre503","theatre503.com",2,"South","Battersea","Wandsworth","Clapham Junction",
  ["text"],"63-seat new-writing hotspot above the Latchmere. The best of the pub theatres."),
 ("white-bear","White Bear Theatre","whitebeartheatre.co.uk",2,"South","Kennington","Lambeth","Kennington",
  ["text"],"50-seat pub theatre since 1988. New writing and the Lost Classics Project."),
 ("golden-goose","Golden Goose Theatre","goldengoosetheatre.co.uk",2,"South-East","Camberwell","Southwark","Denmark Hill",
  ["text"],"100 seats, opened 2020 by the White Bear's former AD. Offie-winning new work."),
 ("bread-and-roses","Bread & Roses Theatre","breadandrosestheatre.co.uk",2,"South","Clapham","Lambeth","Clapham North",
  ["text","devised"],"Above a socialist pub. New writing, devised and improvised work."),
 ("brockley-jack","Brockley Jack Studio","brockleyjack.co.uk",2,"South-East","Crofton Park","Lewisham","Crofton Park",
  ["text"],"50-seat black box. New writing, revivals, scratch nights, multiple Offie wins."),
 ("bridge-house","The Bridge House Theatre","thebridgehousetheatre.co.uk",2,"South-East","Penge","Bromley","Penge West",
  ["text"],"50-seat black box above the pub, by Crystal Palace Park. New writing and the Penge West serial."),
 ("arches-lane","Arches Lane Theatre","archeslanetheatre.com",2,"South","Nine Elms","Wandsworth","Battersea Power Station",
  ["text"],"94 seats in the Power Station arches. Reopened 2025 in the former Turbine space."),
 ("piehouse","Piehouse Co-op","piehouse.coop",2,"South-East","Deptford","Lewisham","Deptford Bridge",
  ["live-art","devised","music-hall"],"Anti-capitalist DIY arts space in a railway arch, reopened 2025 as a workers' co-op. Theatre, folk, jazz, queer cabaret, punk."),
 ("union-theatre","Union Theatre","uniontheatre.biz",2,"South","Southwark","Southwark","Southwark",
  ["text","opera"],"Railway arch fringe venue. Musicals and revivals."),
 ("colour-house","Colour House Theatre","colourhousetheatre.co.uk",2,"South-West","Merton Abbey Mills","Merton","Colliers Wood",
  ["puppetry"],"70-seat studio in a Grade II former dyeing house at a craft village on the Wandle."),
 ("oso-arts","OSO Arts Centre","osoarts.org.uk",2,"South-West","Barnes","Richmond","Barnes Bridge",
  ["text","music-hall"],"130-seat community arts centre in the former sorting office."),
 ("blue-elephant","Blue Elephant Theatre","blueelephanttheatre.co.uk",2,"South-East","Camberwell","Southwark","Oval",
  ["physical","puppetry","devised"],"Surrendered its Camberwell building Dec 2024 after losing NPO funding. Continues as a company — track productions, not the venue."),
 ("lowmac","Lower Marsh Arts Club","vaultcreativearts.com",2,"South","Waterloo","Lambeth","Waterloo",
  ["devised","music-hall"],"VAULT Festival's successor, launching 7 Sept 2026. Up to three shows a night plus three annual festivals."),
 ("calder","Calder Bookshop & Theatre","calderbookshop.com",2,"South","Waterloo","Southwark","Southwark",
  ["text"],"Tiny literary theatre and bookshop on The Cut. Beckett-leaning European drama."),
 ("omnibus-south","Upstairs at the Three Stags","threestagsse1.co.uk",2,"South","Kennington","Lambeth","Lambeth North",
  ["text"],"Small pub room used for fringe runs and scratch nights. Verify current programming."),

 # ---------- TIER 2: East fringe ----------
 ("the-space","The Space","space.org.uk",2,"East","Isle of Dogs","Tower Hamlets","Mudchute",
  ["text","devised"],"Grade II former church. Year-round theatre, music, comedy and dance."),
 ("rose-and-crown","Ye Olde Rose & Crown","yeolderoseandcrown.co.uk",2,"East","Walthamstow","Waltham Forest","Walthamstow Central",
  ["text","music-hall"],"70-seat pub theatre. Cabaret and pop-up variety."),
 ("half-moon","Half Moon Theatre","halfmoon.org.uk",2,"East","Limehouse","Tower Hamlets","Limehouse",
  ["puppetry","devised"],"Specialist young people's theatre; institutionally significant to youth work."),
 ("theatre-deli","Theatre Deli","theatredeli.co.uk",2,"Central","City","City of London","Aldgate",
  ["devised","live-art"],"Meanwhile-use charity turning empty city buildings into rehearsal and performance space."),
 ("cafe-oto","Café OTO","cafeoto.co.uk",2,"East","Dalston","Hackney","Dalston Kingsland",
  ["live-art"],"Not theatre, but the closest London has to a permanent home for the properly experimental."),
 ("vortex","Vortex Jazz Club","vortexjazz.co.uk",2,"East","Dalston","Hackney","Dalston Kingsland",
  ["live-art"],"Improvised and experimental music; occasional performance crossover."),
 ("applecart-arts","Applecart Arts","applecartarts.com",2,"East","Newham","Newham","Plaistow",
  ["devised"],"Small community-rooted venue. Emerging companies and festivals."),
 ("space-arts-brady","Brady Arts Centre","towerhamlets.gov.uk",2,"East","Whitechapel","Tower Hamlets","Whitechapel",
  ["devised"],"Council-run arts centre used for community and small-scale performance."),

 # ---------- roving companies: producer feeds, not venues ----------
 ("darkfield","Darkfield","darkfield.org",1,"roving","varies","—","varies",
  ["immersive","spooky"],"Binaural pieces performed in pitch-black shipping containers. Pop-up locations — follow the company."),
 ("bridge-command","Bridge Command","bridgecommand.co.uk",1,"South","Vauxhall","Lambeth","Vauxhall",
  ["immersive"],"Parabolic Theatre's starship LARP in the arches. Audiences crew the bridge."),
 ("nunkie","Nunkie Theatre Company","nunkie.co.uk",2,"roving","varies","—","varies",
  ["spooky"],"Robert Lloyd Parry's one-man M.R. James ghost stories, candlelit Edwardian-storyteller style. Christmas at the Old Red Lion, then tours."),
 ("charles-court-opera","Charles Court Opera","charlescourtopera.com",2,"roving","varies","—","varies",
  ["opera","music-hall"],"Boutique chamber opera and G&S. Plays Wilton's and Jermyn Street. No home venue."),
 ("ockhams-razor","Ockham's Razor","ockhamsrazor.co.uk",2,"roving","varies","—","varies",
  ["circus","physical"],"Object and aerial company, MimeLondon veterans."),
 ("gecko","Gecko Theatre","geckotheatre.com",2,"roving","varies","—","varies",
  ["physical","devised"],"Physical theatre company; The Wedding is the standard reference."),
 ("zu-uk","ZU-UK","zu-uk.com",2,"East","Hackney Wick","Hackney","Hackney Wick",
  ["immersive","live-art"],"Participatory and one-to-one work, often in east London."),

 # ---------- festivals: date anchors ----------
 ("mimelondon","MimeLondon","mimelondon.com",1,"festival","varies","—","varies",
  ["physical","circus"],"Successor to the London International Mime Festival. Late January, plus occasional autumn slots."),
 ("london-lovecraft","London Lovecraft Festival","londonlovecraft.com",1,"festival","South Kensington","Kensington & Chelsea","Gloucester Road",
  ["spooky","immersive"],"Seven days each February at the Drayton Arms. Sixth year in 2026, expanding into interactive work."),
 ("gdif","Greenwich+Docklands International Festival","festival.org",1,"festival","Greenwich","Greenwich","varies",
  ["physical","immersive","circus"],"Free outdoor festival, late Aug to early Sept. The highest volume of genuinely odd free work in South East London."),
 ("lift","LIFT","liftfestival.com",1,"festival","varies","—","varies",
  ["devised","immersive","live-art"],"Biennial international festival, now led by BAC. Uses the whole city."),
 ("suspense","Suspense Puppetry Festival","suspensefestival.com",1,"festival","varies","—","varies",
  ["puppetry"],"London's adult puppetry festival, autumn, odd-numbered years. Little Angel is a core partner."),
 ("grimeborn","Grimeborn","arcolatheatre.com",1,"festival","Dalston","Hackney","Dalston Junction",
  ["opera"],"Arcola's August alternative opera festival. Bold, low-cost, new and radical stagings."),
 ("spill","SPILL Festival","spillfestival.com",2,"festival","varies","—","varies",
  ["live-art"],"Live art festival; sporadic London editions."),
 ("voila-europe","Voila! Europe","voilafestival.co.uk",2,"festival","varies","—","varies",
  ["devised","physical"],"European theatre festival across small London venues each November."),
]

# already probed — real config carries over
VERIFIED = {
 "arcola": dict(whats_on_url="https://www.arcolatheatre.com/whats-on/",
                fetch_method="static", one_stage=False, platform="wordpress",
                show_url_pattern="/event/{slug}/", pwyc=True,
                typical_price_gbp=[12,39],
                selectors={"show_card":"li:has(h3)","title":"h3",
                           "space":"[class*=venue]","dates":"[class*=date]",
                           "link":"a[href*='/event/']"}),
 "southwark-playhouse": dict(whats_on_url="https://southwarkplayhouse.co.uk/",
                fetch_method="static", one_stage=False,
                platform="wordpress + spektrix",
                show_url_pattern="/productions/{slug}/", pwyc=False,
                typical_price_gbp=[16,24],
                selectors={"show_card":"[class*=production], article",
                           "title":"h2, h3","dates":"[class*=date]",
                           "link":"a[href*='/productions/']"}),
 "wiltons": dict(whats_on_url="https://wiltons.org.uk/whats-on/",
                fetch_method="static", one_stage=False,
                show_url_pattern="/whats-on/{slug}/", pwyc=False,
                typical_price_gbp=[12.5,27],
                selectors={"show_card":"article, [class*=event]",
                           "title":"h2, h3","dates":"[class*=date]",
                           "link":"a[href*='/whats-on/']"}),
 "camden-peoples-theatre": dict(whats_on_url="https://cptheatre.co.uk/Whats-On",
                fetch_method="static", one_stage=True,
                show_url_pattern="/whatson/{slug}", pwyc=False,
                typical_price_gbp=[12,18],
                selectors={"show_card":"[class*=event], article","title":"h3",
                           "dates":"[class*=date], p","blurb":"p",
                           "link":"a[href*='/whatson/']"},
                venue_tag_map={"Puppetry":"puppetry",
                               "Physical Theatre":"physical",
                               "Live Art":"live-art",
                               "Music/Musical":"music-hall"}),
 "the-yard": dict(whats_on_url="https://theyardtheatre.co.uk/whats-on",
                fetch_method="js_rendered", one_stage=False, fallback="search",
                search_query="The Yard Theatre Hackney Wick what's on"),
}

venues = []
for vid, name, domain, tier, compass, area, borough, station, tags, desc in V:
    v = {
        "id": vid, "name": name, "domain": domain, "tier": tier,
        "location": {"area": area, "borough": borough,
                     "compass": compass, "nearest_station": station},
        "tags": tags,
        "description": desc,
        "status": "active",
        "last_verified": "2026-09-05",
    }
    if vid in VERIFIED:
        v.update(VERIFIED[vid])
        v["url_verified"] = True
    else:
        v["whats_on_url"] = None
        v["url_candidates"] = [f"https://{domain}{p}" for p in CANDIDATES]
        v["fetch_method"] = "unverified"
        v["one_stage"] = None
        v["url_verified"] = False
    venues.append(v)

# venues needing a human note
NOTES = {
 "hope-theatre":"Leadership and board changed in 2024; Greene King committed to keeping it open. Re-verify quarterly.",
 "blue-elephant":"Building surrendered Dec 2024. Company continues — treat as a producer feed.",
 "bernie-grant":"Financially precarious; paused some activity in 2025. Re-verify quarterly.",
 "gate-theatre":"Itinerant since 2022. Scrape the company site and follow announced venues.",
 "lowmac":"Launches 7 Sept 2026. Will likely get its own domain — currently under the parent.",
 "little-angel":"Mostly children's puppetry: expect a low hit rate. Filter for visiting companies and heritage events.",
 "camden-peoples-theatre":"Highest volume on the list (~23 events per 8 weeks, mostly one-nighters). Cap picks per venue in the digest.",
 "the-yard":"Next.js. Check for a __NEXT_DATA__ blob before reaching for a headless browser.",
 "arcola":"Listing mixes workshops with productions — drop rows with no Studio 1/2 value.",
 "southwark-playhouse":"Homepage is the listings page. Stage-2 pages carry full pricing tiers, running time, content warnings.",
 "punchdrunk":"One production at a time, booking months ahead. Poll monthly, not weekly.",
 "gdif":"Annual, Aug–Sep, mostly free and unticketed. Poll seasonally.",
 "lift":"Biennial. Poll seasonally.",
 "suspense":"Odd-numbered years. Poll seasonally.",
 "mimelondon":"Announces in autumn for a late-January festival.",
}
for v in venues:
    if v["id"] in NOTES:
        v["notes"] = NOTES[v["id"]]

doc = {
 "meta": {
   "version": "1.0",
   "created": "2026-09-05",
   "timezone": "Europe/London",
   "lookahead_weeks": 8,
   "max_price_gbp": 35,
   "total_venues": len(venues),
   "verified_venues": sum(1 for v in venues if v.get("url_verified")),
   "note": ("Identity fields are researched and stable. Technical fields "
            "(whats_on_url, fetch_method, one_stage, selectors) are unverified "
            "for all but the five probed venues — run probe.py to resolve "
            "url_candidates and write back confirmed values."),
 },
 "tag_vocabulary": ["puppetry","physical","circus","immersive","live-art",
                    "opera","music-hall","spooky","devised","text"],
 "poll_cadence": {
   "weekly": "tier 1 venues with url_verified: true",
   "monthly": "tier 2 fringe, plus Punchdrunk and other long-run venues",
   "seasonal": "festivals (gdif, lift, suspense, mimelondon, london-lovecraft)",
 },
 "venues": venues,
}

out = Path("/mnt/user-data/outputs/venues-full.yaml")
out.write_text(
  "# venues-full.yaml — In the Gods venue registry\n"
  "# Generated 2026-09-05. See meta.note on which fields are trustworthy.\n\n"
  + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=88)
)

from collections import Counter
print(f"{len(venues)} venues")
print("verified :", sum(1 for v in venues if v.get("url_verified")))
print("by tier  :", dict(Counter(v['tier'] for v in venues)))
print("by area  :", dict(Counter(v['location']['compass'] for v in venues)))
print("by tag   :", dict(Counter(t for v in venues for t in v['tags']).most_common()))
print("bytes    :", out.stat().st_size)
