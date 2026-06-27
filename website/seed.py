"""
Seed the database with categories and sample articles.
Run: python seed.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session
from models import Base, Category, Article
from database import engine, SessionLocal, init_db


def seed():
    init_db()

    db = SessionLocal()

    # === Categories ===
    categories_data = [
        {"slug": "noticias", "name": "Noticias", "name_en": "News", "display_order": 1,
         "description": "Las últimas noticias que importan a la comunidad Latina."},
        {"slug": "deportes", "name": "Deportes", "name_en": "Sports", "display_order": 2,
         "description": "Fútbol, NBA, NFL, MLB y más. Toda la acción deportiva."},
        {"slug": "entretenimiento", "name": "Entretenimiento", "name_en": "Entertainment", "display_order": 3,
         "description": "Novelas, celebridades, streaming y todo el chisme."},
        {"slug": "cultura", "name": "Cultura", "name_en": "Culture", "display_order": 4,
         "description": "Arte, identidad, herencia y tradiciones Latinas."},
        {"slug": "musica", "name": "Música", "name_en": "Music", "display_order": 5,
         "description": "Lo último en música Latina: urban, pop, regional y más."},
        {"slug": "comunidad", "name": "Comunidad", "name_en": "Community", "display_order": 6,
         "description": "Inmigración, recursos cívicos, salud y educación."},
    ]

    cat_map = {}
    for cdata in categories_data:
        existing = db.query(Category).filter(Category.slug == cdata["slug"]).first()
        if existing:
            cat_map[cdata["slug"]] = existing
        else:
            cat = Category(**cdata, is_active=True)
            db.add(cat)
            db.flush()
            cat_map[cdata["slug"]] = cat
            print(f"  + Category: {cat.name}")

    # === Sample Articles ===
    now = datetime.utcnow()

    articles_data = [
        {
            "title": "La Selección Mexicana hace historia en el Mundial 2026 con fase de grupos perfecta",
            "slug": "mexico-historia-mundial-2026-fase-grupos-perfecta",
            "category": "deportes",
            "excerpt": "El Tri logró nueve puntos de nueve posibles, clasificando como líder absoluto a la fase de eliminación directa.",
            "body_markdown": """## Un logro sin precedentes

La Selección Mexicana de fútbol ha escrito una página dorada en su historia al conseguir una **fase de grupos perfecta** en el Mundial 2026, sumando nueve puntos de nueve posibles y clasificando como líder absoluto a los dieciseisavos de final.

El equipo dirigido por el cuerpo técnico demostró un nivel de juego que entusiasmó a millones de aficionados dentro y fuera de México.

### Claves del éxito

- **Defensa sólida:** Solo un gol encajado en tres partidos
- **Goles distribuidos:** Seis jugadores diferentes anotaron
- **Afición incondicional:** Los estadios se vistieron de verde en cada partido

> *"Este es el México que todos queríamos ver. La unión del grupo es lo que nos hace fuertes."*

El camino de México continúa en la fase eliminatoria, donde los rivales serán mucho más exigentes.""",
            "meta_description": "México clasifica con puntaje perfecto al Mundial 2026. Nueve de nueve puntos en fase de grupos.",
            "tags": '["Mundial 2026", "Selección Mexicana", "Fútbol"]',
            "content_type": "news",
            "is_featured": True,
            "is_breaking": False,
            "published_hours_ago": 2,
        },
        {
            "title": "Bad Bunny vuelve a reventar las taquillas con su gira mundial",
            "slug": "bad-bunny-gira-mundial-taquillas-2026",
            "category": "musica",
            "excerpt": "El conejo malo supera récords de ventas con su nueva gira que recorre Estados Unidos, México y América Latina.",
            "body_markdown": """## Un fenómeno imparable

Bad Bunny ha demostrado una vez más por qué es uno de los artistas más influyentes de la música urbana a nivel mundial.

Su nueva gira ha vendido más de **dos millones de entradas** en tan solo las primeras semanas de preventa, batiendo todos los registros anteriores en la categoría urbana latina.

### Los números hablan

- **2.3 millones** de entradas vendidas
- Presente en **45 ciudades** de todo el mundo
- Estimado de **$300 millones** en taquilla total

La gira incluye una parada especial en Puerto Rico, tierra natal del artista, donde se esperan múltiples funciones consecutivas con localidades agotadas.""",
            "meta_description": "Bad Bunny supera récords de taquilla con su nueva gira mundial 2026.",
            "tags": '["Bad Bunny", "Música Urbana", "Conciertos"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 5,
        },
        {
            "title": "Comunidad Latina en California se moviliza para ayudar a víctimas del terremoto en Venezuela",
            "slug": "comunidad-latina-california-ayuda-venezuela-terremoto",
            "category": "noticias",
            "excerpt": "Organizaciones comunitarias en Los Ángeles, Sacramento y San Francisco recolectan ayuda humanitaria para los afectados.",
            "body_markdown": """## Solidaridad sin fronteras

La comunidad Latina en California ha respondido rápidamente ante la crisis humanitaria en Venezuela tras los devastadores terremotos que han dejado cientos de víctimas mortales y miles de damnificados.

### Iniciativas en marcha

En **Los Ángeles**, organizaciones como *All for Venezuela* están enviando suministros médicos de primera necesidad, mientras que en el **Área de la Bahía**, el restaurante *Arepas SJ* se ha convertido en un centro de acopio comunitario.

> *"Cuando un Latino sufre, todos sentimos el dolor. Hoy más que nunca necesitamos estar unidos."*

Las personas interesadas en colaborar pueden contactar a las organizaciones a través de sus redes sociales o asistir directamente a los centros de acopio habilitados en distintas ciudades.""",
            "meta_description": "Latinos en California se organizan para enviar ayuda humanitaria a Venezuela.",
            "tags": '["Venezuela", "Terremoto", "Comunidad Latina", "Ayuda Humanitaria"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": True,
            "published_hours_ago": 1,
        },
        {
            "title": "Neymar regresa a la selección brasileña tras casi tres años de ausencia",
            "slug": "neymar-regreso-seleccion-brasilera-2026",
            "category": "deportes",
            "excerpt": "El astro brasileño vuelve a vestir la camiseta amarilla en lo que podría ser su última Copa del Mundo.",
            "body_markdown": """## El regreso del crack

Neymar Jr. ha vuelto a las canchas con la selección brasileña tras casi tres años de ausencia debido a lesiones.

El delantero, que ha sido una de las figuras más mediáticas del fútbol mundial, demostró que su talento sigue intacto en su partido de regreso, donde contribuyó con una asistencia decisiva.

> *"Volver a vestir esta camiseta es un sueño. He pasado por momentos muy difíciles, pero aquí estoy."*

Brasil, que ya había asegurado su clasificación, recibe este refuerzo de lujo para la fase eliminatoria del torneo.""",
            "meta_description": "Neymar regresa a Brasil tras casi 3 años. El astro vuelve para la fase eliminatoria del Mundial 2026.",
            "tags": '["Neymar", "Brasil", "Mundial 2026"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 8,
        },
        {
            "title": "Las tradiciones familiares que definen el verano Latino",
            "slug": "tradiciones-familiares-verano-latino",
            "category": "cultura",
            "excerpt": "Desde los asados dominicales hasta las fiestas patronales, exploramos las costumbres que unen a las familias Latinas.",
            "body_markdown": """## Más que costumbres, son identidad

El verano para las familias Latinas es mucho más que calor y vacaciones. Es la temporada de los **asados familiares**, las reuniones multigeneracionales, la música a todo volumen y esas conversaciones que se extienden hasta la madrugada.

### El arte del asado familiar

No hay nada que represente mejor la unión familiar Latina que un buen asado. Cada región tiene su estilo: en México son las carnitas y el chorizo; en Argentina y Uruguay, el asado de tira; en Colombia, la bandeja paisa compartida.

### Los famos

Las reuniones familiares tienen sus personajes icónicos:

- **La tía que pregunta cuándo te vas a casar**
- **El tío que se duerme en el sillón después de comer**
- **La abuela que insiste en que comas más**
- **Los primos jugando fútbol en el patio hasta que se hace de noche**

> *"La familia es lo más importante. Sin ella, no somos nada."*

Estas tradiciones, transmitidas de generación en generación, son lo que mantiene viva la cultura Latina en Estados Unidos.""",
            "meta_description": "Tradiciones familiares del verano Latino: asados, reuniones y cultura.",
            "tags": '["Cultura", "Familia", "Tradiciones", "Verano"]',
            "content_type": "feature",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 12,
        },
        {
            "title": "Shakira encabezará la ceremonia inaugural del Mundial 2026",
            "slug": "shakira-ceremonia-inaugural-mundial-2026",
            "category": "entretenimiento",
            "excerpt": "La colombiana regresará al escenario que la consagró con el 'Waka Waka' hace más de una década.",
            "body_markdown": """## La loba vuelve al Mundial

**Shakira** ha sido confirmada como la artista principal de la ceremonia de inauguración del Mundial 2026, en lo que será su regreso al escenario futbolístico más grande del mundo.

La barranquillera, cuyo *Waka Waka* se convirtió en el himno oficial del Mundial de Sudáfrica 2010, promete una presentación que celebrará la cultura Latina ante millones de espectadores globales.

### Se espera un show épico

- Repertorio que incluirá éxitos nuevos y clásicos
- Invitados especiales aún por confirmar
- Coreografía con más de 500 artistas en escena

> *"El fútbol y la música son los dos idiomas que unen a nuestra gente. Estoy lista."*

La ceremonia se transmitirá en vivo a más de 200 países.""",
            "meta_description": "Shakira encabezará la ceremonia inaugural del Mundial 2026.",
            "tags": '["Shakira", "Mundial 2026", "Ceremonia Inaugural"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 18,
        },
        {
            "title": "Debate sobre el TPS se reaviva tras crisis humanitaria en Venezuela",
            "slug": "debate-tps-venezuela-crisis-humanitaria-2026",
            "category": "comunidad",
            "excerpt": "El terremoto en Venezuela reabre la conversación sobre protecciones migratorias para los venezolanos en EE.UU.",
            "body_markdown": """## Una conversación urgente

La devastadora crisis humanitaria en Venezuela tras los terremotos ha reavivado el debate sobre el **Estatus de Protección Temporal (TPS)** para los ciudadanos venezolanos que residen en Estados Unidos.

### ¿Qué significa el TPS?

El TPS es una protección temporal que permite a ciudadanos de países afectados por conflictos armados, desastres naturales u otras condiciones extraordinarias vivir y trabajar legalmente en EE.UU.

### Implicaciones actuales

- Aproximadamente **600,000 venezolanos** podrían ser elegibles
- El estatus proporciona autorización de trabajo
- **No** proporciona un camino directo a la residencia permanente

> *"Cuando hay una catástrofe humanitaria de esta magnitud, deportar a las personas de vuelta al desastre no es una opción moral."*

Organizaciones de derechos civiles han pedido al Congreso actuar con urgencia.""",
            "meta_description": "Crisis en Venezuela reaviva el debate sobre TPS para venezolanos en EE.UU.",
            "tags": '["TPS", "Venezuela", "Inmigración", "Comunidad"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 24,
        },
        {
            "title": "El auge del cine Latino: las películas que están cambiando Hollywood",
            "slug": "auge-cine-latino-hollywood-2026",
            "category": "entretenimiento",
            "excerpt": "Directores y actores latinos rompen barreras en una industria históricamente excluyente.",
            "body_markdown": """## Una nueva era para el cine Latino

El cine Latino está viviendo un momento sin precedentes en Hollywood. Con películas que celebran la diversidad, complejidad y riqueza de la cultura Hispana, una nueva generación de creadores está reescribiendo las reglas.

### Rompiendo estereotipos

Durante décadas, los papeles Latinos en Hollywood se limitaban a estereotipos reduccionistas. Hoy, directores como **Alejandro González Iñárritu**, **Guillermo del Toro** y una nueva ola de cineastas independentes están demostrando que las historias Latinas tienen alcance universal.

> *"No queremos ser la nota al pie. Somos protagonistas de nuestra propia historia."*

El futuro del cine Latino es prometedor, con más voces y perspectivas que nunca llegando a las pantallas de todo el mundo.""",
            "meta_description": "El cine Latino en auge: cómo directores y actores cambian Hollywood.",
            "tags": '["Cine", "Hollywood", "Representación Latina"]',
            "content_type": "feature",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 30,
        },
        {
            "title": "Rosalía anuncia gira LUX Tour con paradas en Miami, Los Ángeles y Nueva York",
            "slug": "rosalia-gira-lux-tour-estados-unidos-2026",
            "category": "musica",
            "excerpt": "La catalana llevará su nuevo show visual a las principales ciudades estadounidenses.",
            "body_markdown": """## Motomami en camino

**Rosalía** ha anunciado las fechas norteamericanas de su esperada gira **LUX Tour**, que incluirá paradas en Miami, Orlando, Boston, Los Ángeles y Nueva York.

La catalana, que ha revolucionado la industria con su fusión de flamenco, pop y música urbana, promete un espectáculo visual sin precedentes.

### Setlist destacado

- Temas de su último álbum
- Clásicos como *Despechá* y *SAOKO*
- Colaboraciones sorpresa en cada ciudad

La preventa de entradas comienza la próxima semana.""",
            "meta_description": "Rosalía anuncia gira LUX Tour con fechas en Miami, LA, NYC y más.",
            "tags": '["Rosalía", "Gira LUX Tour", "Música"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 36,
        },
        {
            "title": "Las jugadoras Latinas que están cambiando el fútbol femenino",
            "slug": "jugadoras-latinas-futbol-femenino-cambio",
            "category": "deportes",
            "excerpt": "Desde la NWSL hasta las selecciones nacionales, las Latinas hacen historia en el deporte.",
            "body_markdown": """## Rompiendo barreras

El fútbol femenino Latino está en pleno auge. Cada vez más jugadoras Latinas están demostrando su talento en las ligas más competitivas del mundo.

### Inspiración para las nuevas generaciones

La visibilidad de estas atletas es fundamental para que miles de niñas Latinas sueñen con llegar a lo más alto del deporte.

> *"Cada vez que piso la cancha, juego por todas las niñas que vendrán después de mí."*

El futuro del fútbol femenino es Latina.""",
            "meta_description": "Jugadoras Latinas que hacen historia en el fútbol femenino mundial.",
            "tags": '["Fútbol Femenino", "Deportes", "Mujeres Latinas"]',
            "content_type": "feature",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 48,
        },
        {
            "title": "La cultura del 'fatalismo': por qué los Latinos decimos 'ya le tocaba'",
            "slug": "cultura-fatalismo-latino-ya-le-tocaba",
            "category": "cultura",
            "excerpt": "Una mirada profunda al mindset cultural que ayuda a los Latinos a navegar la adversidad.",
            "body_markdown": """## Cuando la vida da limones...

¿Alguna vez has escuchado a tu mamá o abuela decir ***"ya le tocaba"*** cuando algo malo sucede? No es resignación — es una forma cultural de procesar la adversidad que tiene raíces profundas en la experiencia Latina.

### El fatalismo como herramienta de resiliencia

El **fatalismo** — la creencia de que algunos eventos están determinados por el destino — a menudo se malinterpreta como pasividad. Pero dentro de la cultura Latina, funciona como un mecanismo de resiliencia colectiva.

> *"No es que no nos importe. Es que aceptamos lo que no podemos cambiar y seguimos adelante."*

Entender esta dimensión cultural es clave para comprender cómo las comunidades Latinas han superado siglos de adversidad.""",
            "meta_description": "El fatalismo Latino: por qué decimos 'ya le tocaba' y cómo ayuda a la resiliencia.",
            "tags": '["Cultura", "Fatalismo", "Identidad Latina"]',
            "content_type": "opinion",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 60,
        },
        {
            "title": "Cabo Verde hace historia: el país más pequeño en clasificar a fase eliminatoria del Mundial",
            "slug": "cabo-verde-historia-mundial-2026-pais-mas-pequeno",
            "category": "deportes",
            "excerpt": "La selección africana de medio millón de habitantes logra una hazaña sin precedentes.",
            "body_markdown": """## David contra Goliat

**Cabo Verde**, una nación insular africana con menos de 600,000 habitantes, se ha convertido en el país más pequeño de la historia en clasificar a una fase eliminatoria mundialista.

### Una hazaña histórica

- Superó a Uruguay y Arabia Saudita en su grupo
- Avanzó con **tres empates**, demostrando una solidez defensiva impresionante
- Su población es menor que la de muchas ciudades estadounidenses

> *"Demostramos que el tamaño del país no importa. Lo que importa es el tamaño del corazón."*

La hazaña de Cabo Verde es un recordatorio de que en el fútbol, como en la vida, los sueños no tienen límites.""",
            "meta_description": "Cabo Verde hace historia como el país más pequeño en clasificar a eliminatorias del Mundial.",
            "tags": '["Cabo Verde", "Mundial 2026", "Historia"]',
            "content_type": "news",
            "is_featured": False,
            "is_breaking": False,
            "published_hours_ago": 72,
        },
    ]

    # Insert articles
    for adata in articles_data:
        cat = cat_map[adata["category"]]
        existing = db.query(Article).filter(Article.slug == adata["slug"]).first()
        if existing:
            continue

        published_at = now - timedelta(hours=adata["published_hours_ago"])

        article = Article(
            category_id=cat.id,
            title=adata["title"],
            slug=adata["slug"],
            body_markdown=adata["body_markdown"],
            excerpt=adata["excerpt"],
            meta_description=adata["meta_description"],
            tags=adata["tags"],
            content_type=adata.get("content_type", "news"),
            language="es",
            author_display="Latinos.org",
            quality_score=0.9,
            status="published",
            is_breaking=adata.get("is_breaking", False),
            is_featured=adata.get("is_featured", False),
            published_at=published_at,
            created_at=published_at,
        )
        db.add(article)
        db.flush()
        print(f"  + Article: {adata['title'][:50]}...")

    db.commit()
    db.close()
    print("\n[Seed] Complete!")


if __name__ == "__main__":
    seed()
