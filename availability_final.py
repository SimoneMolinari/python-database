# importo le le librerie necessarie per lo script
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from validate_email import validate_email
import time
import schedule
import smtplib
import json
import mariadb
import sys

try:
	conn = mariadb.connect(
		user="root",
		password="",
		host="192.168.1.100",
		port=3306,
		database="progetto_esame"
		)
except mariadb.Error as e:
	print(f"Error connecting to MariaDB Platform: {e}")
	sys.exit(1)

conn.autocommit = True
cur = conn.cursor()


# destinatario
# receiver_email_id = ["bollitore.fugace@gmail.com"]
# receiver_email_id = []
ASIN = []

def caricaASIN():
	ASIN = []
	# carico gli asin dal db
	cur.execute("select * from prod_table;")

	i = 0
	for (id_prod, stato_prod) in cur:
		if i == 0:
			ASIN.insert(i, [id_prod, stato_prod])
		else:
			ASIN.append([id_prod, stato_prod])
		i+=1

	print(ASIN)
	return ASIN

# ASIN = (['B07ZP5QZX2', 'a'], ['B07SXMZLPK', 'a'])
asin_pos = 0

# setto il webdriver [cabio il PATH se sposto il .exe]
options = webdriver.ChromeOptions()
options.add_experimental_option('excludeSwitches', ['enable-logging'])
options.add_argument('--headless')
options.add_argument('no-sandbox')
PATH = r'/usr/bin/chromedriver'

# script in selenium che mi restituisce la disponibilità del prodotto
def checkAvailability(asin):
	driver = webdriver.Chrome(executable_path=PATH, chrome_options=options)
	# setto il mio URL con l'ASIN del prodotto e apro il web driver 
	url = 'https://www.amazon.it/dp/' + asin
	driver.get(url)
	# array per imagazzinare i dati [0 : availability, 1 : titolo]
	# aspetto che si carichi la pagina e cerco l'elemento availability e il titolo del prodotto,
	# in caso di successo restituisco la stringa e chiudo il driver
	try:
		withelist = ['Disponibilità immediata.', 'Generalmente spedito entro', 'Disponibilità: solo']
		details = []
		element = WebDriverWait(driver, 10).until(
     	   		EC.presence_of_element_located((By.ID, "availability"))
		)
		# devo decodificare i caratteri speciali e ricodificarli per poterli ignorare
		av = element.text
		#print(av)
		pr = -1
		for disp in withelist:
			#print("nel for")
			if (disp in av):
				#print("Prezzo")
				element = WebDriverWait(driver, 10).until(
					EC.presence_of_element_located((By.ID, "priceblock_ourprice"))
				)											
				pr = element.text
				pr = pr.replace(' €', '')
				pr = pr.replace(',','.') 
				pr = float(pr)
				#print(pr)
				break
			else:
				pr = float(-1)
		#print("entrato")
		details.append(av)
		details.append(pr)
	except Exception as e:
		print(e)
	finally:
		driver.quit()
		#print(details)
		return details

# script per inviare l'email al destinatario [devo aggiungere il controllo per il cambio di stato, ma dopo integrazione con DBMS]
def sendemail(availability, product, receiver):
	GMAIL_USERNAME = ""
	GMAIL_PASSWORD = ""

	recipient = receiver
	if(validate_email(recipient, verify=True)):
		body_of_email = product + '\n' + availability + '\n amazon.it/dp/' + product
		email_subject = 'Un prodotto nuovamente disponibile'

		# creo la sessione SMTP di gmail
		s = smtplib.SMTP('smtp.gmail.com', 587)

		# inizio la connessione con TLS (sicurezza)
		s.starttls()

		# Log In del mittente (azienda)
		s.login(GMAIL_USERNAME, GMAIL_PASSWORD)

		# messaggio che deve essere inviato
		headers = "\r\n".join(["from: " + GMAIL_USERNAME,
								"subject: " + email_subject,
								"to: " + recipient,
								"mime-version: 1.0",
								"content-type: text/html"])

		content = headers + "\r\n\r\n" + body_of_email
		s.sendmail(GMAIL_USERNAME, recipient, content)
		s.quit()


def manager(ASIN):
	global asin_pos
	receiver_email_id = []
	# creo un manager che mi gestisce le casistiche dell'invio delle mail
	product = checkAvailability(ASIN[asin_pos][0])
	details = product[0]
	priceprod = product[1]
	print(priceprod)
	print(details + "  " + ASIN[asin_pos][1])
	# lista di mail dei clienti che vogliono essere aggiornati sul prodotto
	cur.execute("SELECT email, first, price FROM maillist_table WHERE id_prod = ?;", (ASIN[asin_pos][0],))
	# carcico la maillist
	i = 0
	for (mail, first, price) in cur:
		if i == 0:
			receiver_email_id.insert(0, [mail, first, price])
		else:
			receiver_email_id.append([mail, first, price])
		i+=1
	print(receiver_email_id)
	for x in range(len(receiver_email_id)):
		state_changed = False
		print(details + " " + ASIN[asin_pos][1])
		print("USO " + receiver_email_id[x][0])
		# array whitelist dispo
		whitelist = [
				'Disponibilità immediata.'
				]
		print(receiver_email_id[x][2])
		# controllo se il prezzo è minore se disponibile
		if(priceprod <= receiver_email_id[x][2] and price != -1):
			# controllo se lo stato del prodotto è uguale a quello vecchio 
			if(details != ASIN[asin_pos][1]):
				print("CAMBIO STATO "+ receiver_email_id[x][0])
				# aggiorno lo stato del prodotto se cambiato
				state_changed = True
				cur.execute("UPDATE prod_table SET stato_prod = ? WHERE id_prod = ?;",
							(details, ASIN[asin_pos][0]))
				
				# se availability è presente nella whitelist allora invio la mail
				if details in whitelist or "Disponibilità: solo" in details:
					sendemail(details.replace("à", "a/'"), ASIN[asin_pos][0], receiver_email_id[x][0])
					print("mando la mail stato " + receiver_email_id[x][0])
			# controllo se la mail ha gia' fatto un ciclo (prima volta che viene aggiornato sul prodotto)
			if(receiver_email_id[x][1] == 0):
				# aggiorno first della tabella (primo ciclo)
				cur.execute("UPDATE maillist_table SET first = 1 WHERE email = ? AND id_prod = ?;", (receiver_email_id[x][0], ASIN[asin_pos][0]))
				print("First " + receiver_email_id[x][0])
				# se availability è presente nella whitelist allora invio la mail e non ha gia' inviato la mail con il cambio di stato
				if (details in whitelist or "Disponibilità: solo" in details) and state_changed == False:
					sendemail(details.replace("à", "a\'"), ASIN[asin_pos][0], receiver_email_id[x][0])
					print("mando mail first  " + receiver_email_id[x][0])

	print("Codice prodotto: " + ASIN[asin_pos][0] + "\nDisponibilità: " + details)


# corpo principale del programma
def routine():
    global asin_pos
    global ASIN
    print("\nTracking....")
    # ricarico / carico gli asin con gli stati aggiornati
    if asin_pos == 0:
    	ASIN = caricaASIN()
    manager(ASIN)
    # cambio posizione asin che esamino
    asin_pos += 1
    if asin_pos > len(ASIN)-1:
        asin_pos = 0
 
# ripeto la routine ogni X secondi
schedule.every(5).seconds.do(routine)

# faccio partire eventuali routine che stanno aspettando
# (in caso ci metta di più di X secondi a completare una routine)
while True:
	schedule.run_pending()
	time.sleep(1)
