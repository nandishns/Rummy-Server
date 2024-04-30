# Execute this class to setup the server and initialize all the APIs

# Importing flask module in the project is mandatory
# An object of Flask class is our WSGI application.
from flask import Flask, request, abort, jsonify, Response
from werkzeug.exceptions import HTTPException

import razorpay
import random

import string
import asyncio
import firebase_admin
import threading
from firebase_admin import credentials, firestore, db
from flask_cors import CORS
import logging
import os
from scoring import *
import re

# Flask constructor takes the name of 
# current module (__name__) as argument.
rummyapp = Flask(__name__)
CORS(rummyapp)
path = r'./rummy-ludo-lkr-firebase-adminsdk-i3nza-26c47f1eeb.json'
cred = credentials.Certificate(path)
firebase_admin.initialize_app(cred)

db = firestore.client()
rummyapp.logger.debug('Connection initialized')


ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
suits = ['heart', 'diamond', 'club', 'spade']


def getNRandomCards(n, perfect = False):

    if perfect:
        selected_cards = [f'{i}_heart' for i in ranks]
        return selected_cards

    
    deck = [(rank, suit) for rank in ranks for suit in suits] 

    # Shuffle the deck
    random.shuffle(deck)

    # Select 11 random cards from the shuffled deck
    selected_cards = random.sample(deck, n)

    selected_cards = [f'{rank}_{suit}' for rank, suit in selected_cards]
    return selected_cards

def getThreadByName(roomId):
    for thread in threading.enumerate():
        if thread.name == roomId:
                return thread

# Spawn a new thread for delay in starting new game. 'winner' field should never be declared prior to
# starting of the game.
class lobbyThread(threading.Thread):
    def __init__(self, wait_interval = 30, db_collection = None, roomType = None, roomId = None):
        super().__init__()
        self._kill = threading.Event()
        self._interval = wait_interval
        self.db_collection = db_collection
        self.roomType = roomType
        self.roomId = roomId

    def run(self):
        rummyapp.logger.debug("Spawned new lobby thread in same process.")
        print("Spawned new lobby thread in same process.")

        self._kill.wait(self._interval)
        
        value = self.db_collection.get()
        value = value.to_dict()

        print('Start new game for pools/deals')
    
        if check_next_game_validity_pools_deals(self.roomType,self.roomId):
            createNewCardsAndStartTimer(self.db_collection,self.roomType,self.roomId)

class gameEndStateThread(threading.Thread):
    def __init__(self, roomType = None, roomId = None):
        super().__init__()
        self.roomType = roomType
        self.roomId = roomId

    def run(self):
        gameEndState(self.roomType,self.roomId)

class countDownThread(threading.Thread):

    def __init__(self, sleep_interval = 45): 
        super().__init__()
        self._kill = threading.Event()
        self._interval = sleep_interval
        self.doc_snapshot = None
        self.doc_change = None
        self.db_collection = None
        self.is_killed = False
        self.server_updated_turn = False
        self.stop_timer = False
        self.doc_watcher = None
        self.roomType = None
        self.roomId = None

    def run(self): 
        rummyapp.logger.debug("Spawned new thread in same process.")
        print("Spawned new thread in same process.")

        self.stop_timer = False
        while True:
            # If no kill signal is set, sleep for the interval,
            # If kill signal comes in while sleeping, immediately
            #  wake up and handle
            rummyapp.logger.debug("Thread is sleeping for ", self._interval , " seconds")
            print("Thread is sleeping for ", self._interval , " seconds")
            is_killed = self._kill.wait(self._interval)
            rummyapp.logger.debug("Thread is killed value is ", is_killed)
            rummyapp.logger.debug("Thread awake")
            print("Thread is killed value is ", is_killed)
            print("Thread awake")
            if not is_killed :
                #General case 1: Timer expired and either user didnt make a move
                rummyapp.logger.debug("Updating game timer to next user as user didnt perform action")
                print("Updating game timer to next user as user didnt perform action")
                doc_ref = self.db_collection.get()
                value = doc_ref.to_dict()
                current_turn = value['currentTurn']
                total_players = value['total_players']
                skip_map = value['skip_map']
                skip_turn = value['skip_turn']
                #Update Game timer
                if( ( self.doc_snapshot is not None) and 
                    ( self.doc_change is not None) and
                    ( self.db_collection is not None) ):
                    updateGameTurn(
                        self.db_collection,
                        current_turn,
                        skip_map,
                        skip_turn,
                        self.roomType,
                        self.roomId
                        )
                    self.server_updated_turn = True

                elif ((self.doc_change is None ) or self.doc_snapshot is None):
                    #Edge case 1: The game has started and no one has made a move yet. This is initial state
                    rummyapp.logger.debug("No one made move initially. Skipping turn")
                    print("No one made move initially. Skipping turn")
                    if len(skip_map) == 0:
                        for i in range(total_players):
                            if i == current_turn:
                                skip_map.append(1)
                            else : 
                                skip_map.append(0)
                    else:
                        skip_user_index_value = skip_map[current_turn] + 1
                        print("Current turn " , current_turn)
                        print("Skip user index value = ",skip_user_index_value)
                        if skip_user_index_value >= 3:
                            if current_turn in skip_turn:
                                pass
                                #checkAndUpdateGameState(value, current_turn)
                            else:
                                skip_turn.append(current_turn)
                        skip_map[current_turn] = skip_user_index_value

                    update_turn(self.roomType,self.roomId)

                    self.db_collection.update({
                        'skip_map': skip_map,
                        'skip_turn': skip_turn
                        })  
                    self.server_updated_turn = True
            # Happy flow. User performed action. No issues
            elif not self.stop_timer :
                rummyapp.logger.debug("User performed action within time. Always reset skip map for user to 0")
                print("User performed action within time. Always reset skip map for user to 0")
                doc_ref = self.db_collection.get()
                value = doc_ref.to_dict()
                skip_map = value['skip_map']
                current_turn = value['currentTurn']
                total_players = value['total_players']
                if len(skip_map) == 0:
                    for i in range(total_players):    
                        skip_map.append(0)     
                else:
                    skip_user_index_value = skip_map[current_turn] + 1
                    if skip_user_index_value >= 3:
                        if current_turn in skip_turn:
                            pass 
                            #checkAndUpdateGameState(value, currentTurn)         
                    skip_map[current_turn] = 0
                self.db_collection.update({
                        'skip_map': skip_map
                        })  
                self.server_updated_turn = False

            self.resetTimer()
            if(self.stop_timer == True):
                rummyapp.logger.debug("Breaking out of while loop. Thread can end peacefully.")
                print("Breaking out of while loop. Thread can end peacefully.")
                break
            
            doc_refs = self.db_collection.get()
            checkAndUpdateGameState(doc_refs)

    # Stop timer stops the timer but does not end while loop in run() method. It just awakes the thread if it is sleeping. Usefull for updating 
    # user turns
    def stopTimer(self):
        if(self.server_updated_turn):
            return
        self._kill.set()

    # End timer kill the thread. Signifies the game is over
    def endTimer(self):
        if self.doc_watcher != None :
            rummyapp.logger.debug("Ending timer")
            self.doc_watcher.unsubscribe()
            self.stop_timer = True
            self._kill.set()

    def updateGameState(self, doc_snapshot,doc_changes):
        if(not self.server_updated_turn):
            self.doc_snapshot = doc_snapshot
            self.doc_change = doc_changes

    def resetTimer(self):
        if self._kill.is_set() :
                self.is_killed = False
                self._kill.clear()

    def initDocumentWatcher(self, roomType, roomId):
        #Start watching the document for updates
        self.roomType = roomType
        self.roomId = roomId
        db_collection = db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId)
        self.doc_watcher = db_collection.on_snapshot(on_snapshot)
        self.db_collection = db_collection
    
def createNewCardsAndStartTimer(db_collection,roomType,roomId):
    print("In createNewCardsAndStartTimer")
    value = db_collection.get()
    value = value.to_dict()
    cards = value['cards']
    roomSize = value['current_number']
    newCards = {}
    for user in cards.keys():
        print("User id" ,user)
        newCards[user] = getNRandomCards(13, False)

    print('New card', newCards)

    mapping = {
            'cards': newCards,
            'open_card': getNRandomCards(1)[0], 
            'joker': getNRandomCards(1)[0],
            'skip_map': [],
            'current_game': firestore.Increment(1),
            'score_card_sets': {},
            'score_counter': 0,
            'fold': [],
            'drop': [],
            'pause': False,
            'roundWinner': None,
            'winner': None
        }
    if roomSize == 2:
        print("PRATIK resetting skip turn for 2 players")
        mapping['skip_turn'] = []

    print("PRATIK Mapping for create new cards and start timer", mapping)

    db_collection.update(mapping)

    timerThread = countDownThread(sleep_interval=30)
    timerThread.name = roomId
    timerThread.initDocumentWatcher(roomType= roomType, roomId=roomId)
    timerThread.start()

def updateGameTurn(db_collection, current_turn, skip_map, skip_turn,roomType,roomId):
    if len(skip_map) != 0:
        print(skip_map,current_turn)
        skip_user_index_value = skip_map[current_turn] + 1
        if skip_user_index_value >= 3:
            if current_turn in skip_turn:
                pass
                #checkAndUpdateGameState(value,current_turn)
            else:
                skip_turn.append(current_turn)
        skip_map[current_turn] = skip_user_index_value

    update_turn(roomType,roomId)
    mapping = {
        'skip_map': skip_map,
        'skip_turn': skip_turn
                }
    rummyapp.logger.debug("Updated turn")
    db_collection.update(mapping)
    return

def on_snapshot(doc_snapshot, doc_changes, read_time):
    for change in doc_changes:
        if change.type.name == 'MODIFIED':
            value = doc_snapshot[0].to_dict()
            rummyapp.logger.debug('Document snapshot', value)
            roomId = value['roomId']
            timerThread = getThreadByName(roomId)
            timerThread.updateGameState(doc_snapshot,change)
            

@rummyapp.route('/')
def server_status():
    return 'Server is up and running'

client = razorpay.Client(auth=("rzp_test_fRiWg6WCX5uf7d", "<YOUR_API_SECRET>"))
client.set_app_details({"title" : "Rummy", "version" : "1.0"})

@rummyapp.route('/createOrder')
def generateOrderIdForUser(): 
    userId = str(request.args.get('userID'))  # User ID is the ID which the app sends which is same as firebase user account id
    amount = str(request.args.get('amount')) # Amount for which the user is trying to reload
    data = { "amount": amount, "currency": "INR", "receipt": generateOrderReceipt(userId) } 
    payment = client.order.create(data=data)
    return str(payment)
    

# Method to generate a unique order receipt id for every create order request
# This method returns the hashed user id along with random string to uniquely identify.
# Can be used to internally validate order receipts id 
def generateOrderReceipt(userId):
    return str(hash(userId)) + "-" + str(hash(random.randint(1,100000)))

@rummyapp.route('/createRoom/', methods = ['POST'])
def generateRoom():
    data = request.json
    userId = data.get('userId', '')
    name = data.get('name', '')
    cash = data.get('cash', None)
    pointsConversion = data.get('pointConversion', None)
    roomType = data.get('roomType', '')
    roomSize = data.get('roomSize', 2)
    generateCode = data.get('generateCode', False)

    cards_as_strings = getNRandomCards(13, perfect=False)

    if cash == None and pointsConversion != None:
        cash = pointsConversion * 80
    
    #roomSize = 3
    room_number = createRoom(userId, roomType = roomType, roomSize=roomSize, cards = cards_as_strings, name = name, cash= cash, generateCode  = generateCode)

    if room_number == 220:
        return jsonify({"error": 220})
    map = {
        'cards': [cards_as_strings[:4], cards_as_strings[4:7], cards_as_strings[7:10], cards_as_strings[10:]],
        'room_number': room_number,
    }
    return jsonify(map)

def generateAlphaNumeric(length):
    characters = string.ascii_letters + string.digits

    # Generate the random alphanumeric string
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

def consumeCash(userId, cash):
    try:
        userTransaction = db.collection('transactions').document(userId).get()
        userTransactionDoc = userTransaction.to_dict()
        fundStatus = (userTransactionDoc['balance'] >= cash)

        if fundStatus:
            db.collection('transactions').document(userId).update({
                'balance': firestore.Increment(-1 * cash),
                'lastTransaction': firestore.SERVER_TIMESTAMP,
            })
            db.collection('transactions').document(userId).collection('transactions').add({
                'amount': cash,
                'processedAt': firestore.SERVER_TIMESTAMP,
                'transactionType': 'bet',
            })

        return fundStatus 
    except:
        return False
    
async def depositCash(userId, cash):
    try:
        task = []
        task.append( db.collection('transactions').document(userId).update({
            'balance': firestore.Increment(cash),
            'lastTransaction': firestore.SERVER_TIMESTAMP,
        }))
        task.append(await db.collection('transactions').document(userId).collection('transactions').add({
            'amount': cash,
            'processedAt': firestore.SERVER_TIMESTAMP,
            'transactionType': 'win',
        }))

        await asyncio.gather(*task)

    except:
        return False
    

def createRoom(userId, roomType, roomSize, cards, name, cash, generateCode):
    db_collection = db.collection('games').document(roomType).collection(f'{roomType}_games')

    if (cash == None):
        query = None
        if (not generateCode):
            query = db_collection.where('total_players', '==', roomSize).where('current_number', '<', roomSize).get()
    else:
        fundStatus = consumeCash(userId, cash)
        if (fundStatus):
            query = db_collection.where('total_players', '==', roomSize).where('current_number', '<', roomSize).where('cash', '==', cash).get()
        else:
            return 220

    first_id = None

    if (query != None):
        for doc in query:
            first_id = doc.id
            document = doc.to_dict()
            card_dict = document['cards']
            card_dict[userId] = cards
            mapping = {
                'current_number': firestore.Increment(1), 
                'players': firestore.ArrayUnion([userId]), 
                'cards': card_dict,
                'roomId': first_id
                }

            db_collection.document(first_id).update(
                mapping
            )

            db_collection.document(first_id).collection('scores').document(userId).set({'name': name, 'points': 0, 'id': userId})

            rummyapp.logger.debug("PRATIK document dict",document["current_number"])
            if((document["current_number"] + 1) == document["total_players"]):
                # Last person for the lobby joined. Start game timer
                
                timerThread = countDownThread(sleep_interval=30)
                timerThread.name = first_id
                timerThread.initDocumentWatcher(roomType= roomType, roomId=first_id)
                timerThread.start()

            return first_id
    
    data_map = {
            'total_players': roomSize, 
            'current_number': 1, 
            'skip_turn': [], 
            'skip_map': [],
            'players': [userId], 
            'currentTurn': random.randint(0, roomSize-1), 
            'open_card': getNRandomCards(1)[0], 
            'joker': getNRandomCards(1)[0],
            'cards': {userId: cards},
            'current_game': 0,
            'roomId': first_id,
            'score_card_sets': {},
            'score_counter': 0,
            'fold': [],
            'drop': [],
            }
    
    if roomType == 'pools' or 'deals':
        data_map['old_cards'] = {}
    
    if (generateCode):
        data_map['code'] = generateAlphaNumeric(8)

    if (roomType == 'deals'):
        data_map['max_games'] = 3

    # if (roomType == 'pools'):
    #     data_map['scores'] = [{'name': '', 'id': userId, 'points': 0}]

    if (cash != None):
        data_map['cash'] = cash


    doc_ref = db_collection.add(data_map)
    first_id = doc_ref[-1].id

    db_collection.document(first_id).collection('scores').document(userId).set({'name': name, 'points': 0, 'id': userId})

    return first_id

@rummyapp.route('/joinWithCode/', methods = ["POST"])
def joinWithCode():
    data = request.json
    userId = data.get('userId', '')
    name = data.get('name', '')
    roomType = data.get('roomType', '')
    code = data.get('code', '')

    db_collection = db.collection('games').document(roomType).collection(f'{roomType}_games')

    query = db_collection.where('code', '==', code).get()
    for doc in query:
        first_id = doc.id
        document = doc.to_dict()
        card_dict = document['cards']
        card_dict[userId] = getNRandomCards(13, perfect=False)
        cards_as_strings = card_dict[userId]
        mapping = {
            'current_number': firestore.Increment(1), 
            'players': firestore.ArrayUnion([userId]), 
            'cards': card_dict
            }

        db_collection.document(first_id).update(
            mapping
        )

        db_collection.document(first_id).collection('scores').document(userId).set({'name': name, 'points': 0, 'id': userId})
        return jsonify({'room_number': first_id, 'cards': [cards_as_strings[:4], cards_as_strings[4:7], cards_as_strings[7:10], cards_as_strings[10:]],})
    return jsonify({"error": 230,})
    


def setOpenCard(roomId, card, roomType):
    db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({'open_card': card})
    return

# Fetch new random card which is drawn by user
@rummyapp.route('/getNext/', methods = ['POST'])
def nextCard():
    data = request.json
    userId = data.get('userId', '')
    roomType = data.get('roomType', '')
    roomId = data.get('roomId', 2)
    
    value = db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).get()
    value = value.to_dict()
    rummyapp.logger.debug(value)

    assert (value['currentTurn'] == value['players'].index(userId) == value['currentTurn'])
    card = getNRandomCards(1)[0]
    
    return jsonify({"card": card})

async def declareWinner(winner, roomId, roomType):
    roomRef = get_room_doc_ref(roomType, roomId)

    roomDict = roomRef.to_dict()

    if roomType == 'pools' or roomType == 'deals':
        write_round_winner_to_db(winner,roomType,roomId)
    else:        
        write_winner_to_db(winner,roomType,roomId)
    
    multiple = 1.8

    # Cash handling for cash mode
    if ('cash' not in roomDict): return None
    if ('winner' not in roomDict): return None

    if (roomType != 'points'):
        wonCash = roomDict['cash'] * multiple
        await depositCash(winner, wonCash)
        return None
    
    score_docs = get_score_doc(roomType, roomId)

    tasks = []
    prize = 0
    pointMultiple = 0.8

    for doc in score_docs: 
        doc_data = doc.to_dict()
        doc_id = doc.id
        if (doc_id == winner):
            continue
        doc_score = doc_data['score']
        cash = (doc_score * roomDict['cash']) / 80
        prize += roomDict['cash'] - cash
        tasks.append(depositCash(doc_id, cash))

    tasks.append(depositCash(winner, roomDict['cash'] + prize * pointMultiple))
    await asyncio.gather(*tasks)
    return None

def checkAndUpdateGameState(doc_ref):
    print("In check and update game state logic")
    value = doc_ref.to_dict()
    current_turn = value['currentTurn']
    skip_turn = value['skip_turn']
    total_players = value['total_players']
    roomId = value['roomId']
    timerThread = getThreadByName(roomId)

    if len(skip_turn) == 0: return

    print("Skip turn: ", skip_turn)
    print("Current turn", current_turn)
    #If total players minus skip turns players = 1, that means you have reached end state
    if (total_players - len(skip_turn) == 1):
        write_dummy_winner_to_db(timerThread.roomType, timerThread.roomId)
        timerThread.endTimer()

    return

def invokeSingleInstanceOfGameThread(roomType,roomId):
    gameEndThread = getThreadByName(roomType+roomId)
    if gameEndThread == None:
        print("Creating new instance of gameEndState")
        gameEndThread = gameEndStateThread(roomType,roomId)
        gameEndThread.name = roomType + roomId
        gameEndThread.start()
        gameEndThread.join()


#TODO Add comments
def gameEndState(roomType, roomId):
    rummyapp.logger.debug("In game end state logic")
    print("In game end state logic.")

    doc_ref = get_room_doc_ref(roomType, roomId)
    doc_ref = doc_ref.to_dict()
    
    # Check if fold value equals to winner value. If true, correct fold else wrong fold
    fold_user_id = doc_ref['fold']
    dropped_users = doc_ref['drop']
    print('fold_user_id', fold_user_id)
    if len(dropped_users) != 0:
        update_score_for_dropped_users(roomType,roomId)
    # Always exclude dropped players when performing score calculation for below code block
    if len(fold_user_id) != 0:
        print("Condition one")
        rummyapp.logger.debug("Condition one")
        # Someone folded. First validate if it is correct fold, then perform below actions
        fold_user_card_set = get_card_set_for_player(fold_user_id,roomType,roomId)
        is_perfect_set, score = validate_grouped_cards(fold_user_card_set, doc_ref['joker'])

        if is_perfect_set:
            # Correct fold. User gets 0 points, rest gets their calculated scores.
            # Everyone who dropped gets 40 points, winner 0, rest get their calculated score
            # Do nothing for correct fold. For other players who are part of the lobby, get their card set and calculate score
            for index, player in enumerate(doc_ref['players']):
                if fold_user_id == player:
                    continue
                if player not in doc_ref['drop']:
                    card_set = get_card_set_for_player(player,roomType,roomId)
                    is_perfect_set, score = validate_grouped_cards(card_set, doc_ref['joker'])
                    update_user_score(player, roomType, roomId, score)
            write_winner_to_db(fold_user_id,roomType,roomId)

        else :
            # Wrong fold
            update_user_score(fold_user_id, roomType, roomId, 80)
            write_winner_to_db("Wrong Fold",roomType,roomId)

    elif fold_user_id == None or fold_user_id == []:
        print("Condition two")
        rummyapp.logger.debug("Condition two")
        # Check total players minus skip turn player equals one. If not, game has entered invalid state
        if(doc_ref['total_players'] - len(doc_ref['skip_turn'])) == 1:
            print("Inside condition two")
            rummyapp.logger.debug("Inside condition two")
            # Check if user continuously skipped. allocate that user 80 points
            skip_turn = doc_ref['skip_turn']
            skip_map = doc_ref['skip_map']
            players = doc_ref['players']
            for skips in skip_turn:
                if (skip_map[skips] >= 3):
                    print("Player getting 40 points due to inactivity", players[skips])
                    rummyapp.logger.debug("Player getting 40 points due to inactivity", players[skips])
                    update_user_score(players[skips], roomType, roomId, 40)
            return None
        else:
            raise Exception("Game is in an invalid state")
    elif fold_user_id != []:
        print("Condition three")
        rummyapp.logger.debug("Condition three")

        print("fold_user_id",fold_user_id)
        # Wrong fold. User gets 80 points, dropped users get 40, rest 0
        update_user_score(fold_user_id, roomType, roomId, 80)
        write_winner_to_db("Wrong Fold",roomType,roomId)    
    return None        
            
# TODO: Dynamic cards
@rummyapp.route('/score/', methods=['POST'])
def collectScores():
    data = request.json

    userId = data.get('userId', '')
    roomId = data.get('roomId', '')
    grouped_cards = data.get('cards', '')
    fold = data.get('fold', False)
    roomType = data.get('roomType', '')
    
    ref = get_room_doc_instance(roomType,roomId)
    value = ref.get()
    value = value.to_dict()

    # Store the card sets on firebase server
    score_card_sets = {}
    for i, card in enumerate(grouped_cards):
        score_card_sets[userId+"_set"+str(i)] = card
    ref.update({
        'score_card_sets' : firestore.ArrayUnion([score_card_sets]),
        'score_counter' : firestore.Increment(1)
    })

    if fold:
        ref.update({
            'fold': userId
        })
    
    is_perfect_set, score = validate_grouped_cards(grouped_cards, value['joker'])
    if is_perfect_set:
        if roomType == 'points':
            write_winner_to_db(userId,roomType,roomId)
        elif roomType == 'pools' or roomType == 'deals':
            write_round_winner_to_db(userId,roomType,roomId)

    # Fetch updated ref
    ref = get_room_doc_instance(roomType,roomId)
    newValue = ref.get()
    newValue = newValue.to_dict()
    totalPlayers = newValue['total_players']

    print("score counter", newValue['score_counter'])
    if totalPlayers == newValue['score_counter']:
        # Game end state. Validate scores and declare correct winner
        print("Invoked from collect scores")
        invokeSingleInstanceOfGameThread(roomType,roomId)

    # Calculate the score and get game end state. Then only proceed to create waiting lobby timer and old cards
    if (roomType == 'pools' or roomType == 'deals'): 
        print("Storing old cards for pools/deals game mode")
        is_next_game_valid = check_next_game_validity_pools_deals(roomType,roomId)
        if not is_next_game_valid:
            # End game
            print("Is next game valid", is_next_game_valid)
            isExistingThread = getThreadByName(roomId)
            if isExistingThread != None:
                # Kill the timer
                pass
            return "Success"
        db_collection = get_room_doc_instance(roomType,roomId)
        db_ref = db_collection.get()
        db_ref = db_ref.to_dict()
        old_cards = {}
        for players in db_ref['players']:
                if players == userId:
                    for i, card in enumerate(grouped_cards):
                        old_cards[userId+"_set"+str(i)] = card
        db_collection.update({
            'old_cards': firestore.ArrayUnion([old_cards]),
            'pause': True
        })
        isExistingThread = getThreadByName(roomId)
        if isExistingThread == None:
            waitingLobbyThread = lobbyThread(wait_interval = 60, db_collection= db_collection,roomType=roomType,roomId=roomId)
            waitingLobbyThread.name = roomId
            waitingLobbyThread.start()
            return "Success"

        return "Success"

    return 'Success'


# TODO: Dynamic cards
@rummyapp.route('/throwCard/', methods=['POST'])
def throwCard():
    data = request.json

    userId = data.get('userId', '')
    roomId = data.get('roomId', '')
    fold = data.get('fold', False)
    cardName = data.get('throw', '')
    roomType = data.get('roomType', '')
    rummyapp.logger.debug(fold)
    timerThread = getThreadByName(roomId)
    
    if(fold):
        rummyapp.logger.debug("End timer before running fold logic. ")
        timerThread.endTimer()
    else:            
        timerThread.server_updated_turn = False
        timerThread.stopTimer()

    db_collection = get_room_doc_ref(roomType,roomId)
    value = db_collection.to_dict()

    assert (value['currentTurn'] == value['players'].index(userId) == value['currentTurn'])
    # If assertion fails and game mode is cash, revert the game money to users because this is server issue.
    # Client server out of sync if assertion fails.

    # Update turn
    update_turn(roomType,roomId)
    if fold:
        get_room_doc_instance(roomType,roomId).update({
            'fold': userId
        })
        add_user_to_skip_turn(roomType,roomId,userId)

        # Write dummy winner so that client can invoke /score api and actual winner can be calculated
        write_dummy_winner_to_db(roomType,roomId)
        return "Success"

    setOpenCard(roomId, cardName, roomType)

    return "Success"

@rummyapp.route('/drop/', methods = ['POST'])
async def drop_game():
    data = request.json
    userId = data.get('userId', '')
    roomId = data.get('roomId', '')
    roomType = data.get('roomType', '')

    # Update turn
    add_user_to_skip_turn(roomType,roomId,userId)

    # Fetch updated db state
    db_collection = get_room_doc_ref(roomType,roomId)
    value = db_collection.to_dict()

    get_room_doc_instance(roomType,roomId).update({
        'drop': firestore.ArrayUnion([userId])
    })

    # This handling is for players where all players dropped except 1
    if (value['total_players'] - len(value['skip_turn'])) == 1:
        timerThread = getThreadByName(roomId)
        timerThread.endTimer()
        # Write dummy winner so that client can invoke /score api and actual winner can be calculated
        write_dummy_winner_to_db(roomType,roomId)

    return "Success"  

# Check if next contiguous game for pools or deals mode is valid. If valid ie. next game can begin,
# return true which means declare dummy_winner, else return false and directly declare winner
def check_next_game_validity_pools_deals(roomType, roomId):
    doc_ref = get_room_doc_ref(roomType,roomId)
    doc_ref = doc_ref.to_dict()
    if roomType == 'pools':
        # Iterate through scores of every player and check if anyone exceeds 200 points
        for player in doc_ref['players']:
            user_score = get_user_score_doc_ref(player,roomType,roomId).get()
            user_score = user_score.to_dict()
            if user_score['points'] > 200:
                add_user_to_skip_turn(roomType,roomId,player)
                return False

    if roomType == 'deals':
        max_games = doc_ref['max_games']
        current_game = doc_ref['current_game']

        if current_game > max_games -1:
            return False
        else:
            return True
        
    return True


def get_card_set_for_player(userId ,roomType,roomId):
    validate_room_info(roomType,roomId)
    doc_ref = get_room_doc_ref(roomType,roomId)
    doc_ref = doc_ref.to_dict()
    score_card_sets = doc_ref['score_card_sets']
    card_sets = []
    for sets in score_card_sets:
        # sets corresponds to single player
        for key, value in sets.items():
            newKey = key.split('_')[0]
            if newKey == userId:
                card_sets.append(value)
    print("get_card_set_for_player Card set ",card_sets)
    return card_sets


def update_turn(roomType, roomId):
    validate_room_info(roomType,roomId)
    doc_ref = get_room_doc_ref(roomType,roomId)
    doc_ref = doc_ref.to_dict()
    current_number = doc_ref['current_number']
    current_turn = doc_ref['currentTurn']
    skip_turn = doc_ref['skip_turn']
    total_players = doc_ref['total_players']

    if (total_players - len(skip_turn)) == 1:
        return
    next = current_turn + 1
    next = next % current_number
    while next in skip_turn:
        next += 1
        next = next % current_number
    
    db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({
        'currentTurn': next
    })

def add_user_to_skip_turn(roomType, roomId, userId):
    validate_room_info(roomType,roomId)
    doc_ref = get_room_doc_ref(roomType,roomId)
    doc_ref = doc_ref.to_dict()
    userIndex = doc_ref['players'].index(userId)
    db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({
        'skip_turn': firestore.ArrayUnion([userIndex])
    })

def update_score_for_dropped_users(roomType, roomId):
    validate_room_info(roomType,roomId)
    doc_ref = get_room_doc_ref(roomType,roomId)
    doc_ref = doc_ref.to_dict()
    dropped_users = doc_ref['drop']
    
    for user in dropped_users:
        print("Assigning 40 points for user", user, "for dropping")
        get_user_score_doc_ref(user,roomType,roomId).update({
            'points': firestore.Increment(40)
        })

def get_room_doc_ref(roomType, roomId):
    validate_room_info(roomType,roomId)
    return db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).get()

def get_room_doc_instance(roomType, roomId):
    validate_room_info(roomType,roomId)
    return db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId)

def get_score_doc(roomType,roomId):
    validate_room_info(roomType,roomId)
    score_doc = db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).collection('scores').get()
    score_doc = score_doc.to_dict()
    return score_doc

def get_user_score_doc_ref(userId, roomType, roomId):
    validate_room_info(roomType,roomId)
    return db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).collection('scores').document(userId)

def update_user_score(userId, roomType, roomId, score):
    print("Adding score", score, "for user ", userId)
    get_user_score_doc_ref(userId, roomType, roomId).update({
        'points': firestore.Increment(score)
    })

def write_winner_to_db(winner,roomType,roomId):
    validate_room_info(roomType,roomId)
    # Check if game type is pools or deals. If so, check players points > 200 or player games equals max games. If so write to winner variable
    is_valid = check_next_game_validity_pools_deals(roomType,roomId)
    if is_valid:
        print("Next game for ", roomType, " is valid. Continue new game")
        write_round_winner_to_db(winner,roomType,roomId)
    else:
        db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({'winner': winner})
    return

def write_dummy_winner_to_db(roomType,roomId):
    validate_room_info(roomType,roomId)
    if roomType == 'points':
        db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({'winner': 'dummy_winner'})
    if roomType == 'pools' or roomType == 'deals':
        print("Writing dummy winner to roundWinner")
        db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({'roundWinner': 'dummy_winner'})

def write_round_winner_to_db(winner, roomType, roomId):
    validate_room_info(roomType,roomId)
    db.collection('games').document(roomType).collection(f'{roomType}_games').document(roomId).update({'roundWinner': winner})
    return

def validate_room_info(roomType,roomId):
    if roomType == None or roomId == None or roomType == '' or roomId == '':
        print("Room Type:", roomType)
        print("Room Id", roomId)
        raise ValueError("Values'roomType' or 'roomId' cannot be null")

if __name__ == '__main__':
    rummyapp.debug = True
    if os.environ.get("IS_RUNNIN_ON_AWS",0) == 1:
        rummyapp.run(threaded = True, host='0.0.0.0')
    else:
        rummyapp.run(threaded = True)
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    rummyapp.logger.handlers = gunicorn_logger.handlers
    rummyapp.logger.setLevel(gunicorn_logger.level)
