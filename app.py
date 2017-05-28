import os
import sys
import json
import searchengine
from nltk.stem import porter

import requests
from flask import Flask, request

app = Flask(__name__)

domain = 'https://techfugees/'
search = searchengine.Searcher('searchindex.db')

score_idx = 0
url_idx = 1

stemmer = porter.PorterStemmer()

food_list = [stemmer.stem(w) for w in ['hungry', 'food', 'eat', 'drink', 'water', 'kebab', 'thirsty']]
med_list = [stemmer.stem(w) for w in
            ['doctor', 'hospital', 'ambulance', 'prescription', 'asthma', 'bronchitis', 'cancer', 'disorder',
             'insulin', 'diabetes', 'pain', 'hurt', 'vomit', 'aid', 'ache', 'cough', 'seizure', 'labour',
             'headache', 'weak', 'numb', 'pregnant', 'medical', 'drugs']]
azil_list = [stemmer.stem(w) for w in ['home', 'bed', 'sleep', 'asylum', 'shower', 'nursery', 'shelter']]
legal_list = [stemmer.stem(w) for w in ['papers', 'law', 'process']]
educ_list = [stemmer.stem(w) for w in ['education']]
nonfood_list = [stemmer.stem(w) for w in ['education']]
transp_list = [stemmer.stem(w) for w in ['transport']]
work_list = [stemmer.stem(w) for w in ['work']]
children_list = [stemmer.stem(w) for w in ['children']]


@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200


@app.route('/', methods=['POST'])
def webhook():
    # endpoint for processing incoming messaging events

    data = request.get_json()
    log(data)  # you may not want to log every incoming message in production, but it's good for testing

    if data["object"] == "page":

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:

                if messaging_event.get("message"):  # someone sent us a message

                    sender_id = messaging_event["sender"]["id"]  # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"][
                        "id"]  # the recipient's ID, which should be your page's facebook ID
                    message_text = messaging_event["message"]["text"]  # the message's text

                    msage = guidme_responder(message_text)
                    send_message(msage)

                    msg = responder(message_text)
                    send_message(sender_id, msg)

                if messaging_event.get("delivery"):  # delivery confirmation
                    pass

                if messaging_event.get("optin"):  # optin confirmation
                    pass

                if messaging_event.get("postback"):  # user clicked/tapped "postback" button in earlier message
                    pass

    return "ok", 200


def send_message(recipient_id, message_text):
    log("sending message to {recipient}: {text}".format(recipient=recipient_id, text=message_text))

    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)
    if r.status_code != 200:
        log(r.status_code)
        log(r.text)


def log(message):  # simple wrapper for logging to stdout on heroku
    print(str(message))
    sys.stdout.flush()


def guidme_responder(message):
    query_words = message.split(' ')
    urls = []
    categories = 'categories/'
    for word in query_words:

        if word in med_list:
            urls.append(domain + categories + '1')
        if word in legal_list:
            urls.append(domain + categories + '2')
        if word in food_list:
            urls.append(domain + categories + '3')
        if word in educ_list:
            urls.append(domain + categories + '4')
        if word in nonfood_list:
            urls.append(domain + categories + '5')
        if word in transp_list:
            urls.append(domain + categories + '6')
        if word in azil_list:
            urls.append(domain + categories + '7')
        if word in work_list:
            urls.append(domain + categories + '8')
        if word in children_list:
            urls.append(domain + categories + '9')

    resp_message = "I'm sure these informations from our website will be quite usefull."
    resp_message += '\n'.join(urls)
    return resp_message


def responder(message):
    response = search.query(message)
    resp_message = ''
    if response[0][score_idx] == -1.0:
        resp_message += "I'm not sure what you asked me, check if you made any typo. " \
                        "In any case check this website for additional information: "
        resp_message += response[0][url_idx]
        return resp_message
    else:
        resp_message += "I belive this websites could help you, check it out."
        max_score = response[0][score_idx]
        urls = []
        for i in range(len(response)):
            if max_score - response[i][score_idx] > 2:
                break
            urls.append(response[i][url_idx])
        resp_message += '\n'.join(urls)
        return resp_message


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
