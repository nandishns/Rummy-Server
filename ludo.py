from flask import Flask, request, abort, jsonify, Response
import random
import asyncio
import threading
import string
import firebase_admin
from firebase_admin import credentials, firestore, db
from typing import Optional
from flask_cors import CORS
import logging

ludoapp = Flask(__name__)
CORS(ludoapp)

path = r'./rummy-ludo-lkr-firebase-adminsdk-i3nza-26c47f1eeb.json'
cred = credentials.Certificate(path)
#Uncomment this line when you want to run ludo.py as a standalone app for local testing
#For aws server, we are using wsgi interface which requires only one instance of firebase, else
#exception is thrown. Do not uncomment this code in aws production env
#firebase_admin.initialize_app(cred)

db = firestore.client()

colors = set(["green", "yellow", "red", "blue"])

PAWNS_PER_PLAYER = 4

class Path:
    greenPath = [
        [6, 1], [6, 2], [6, 3], [6, 4], [6, 5],
        [5, 6], [4, 6], [3, 6], [2, 6], [1, 6], [0, 6], [0, 7],
        [0, 8], [1, 8], [2, 8], [3, 8], [4, 8], [5, 8],
        [6, 9], [6, 10], [6, 11], [6, 12], [6, 13], [6, 14],
        [7, 14], [8, 14], [8, 13], [8, 12], [8, 11], [8, 10], [8, 9],
        [9, 8], [10, 8], [11, 8], [12, 8], [13, 8], [14, 8], [14, 7], [14, 6],
        [13, 6], [12, 6], [11, 6], [10, 6], [9, 6],
        [8, 5], [8, 4], [8, 3], [8, 2], [8, 1], [8, 0],
        [7, 0], [7, 1], [7, 2], [7, 3], [7, 4], [7, 5], [7, 6]
    ]

    yellowPath = [
        [1, 8], [2, 8], [3, 8], [4, 8], [5, 8],
        [6, 9], [6, 10], [6, 11], [6, 12], [6, 13], [6, 14],
        [7, 14], [8, 14], [8, 13], [8, 12], [8, 11], [8, 10], [8, 9],
        [9, 8], [10, 8], [11, 8], [12, 8], [13, 8], [14, 8], [14, 7], [14, 6],
        [13, 6], [12, 6], [11, 6], [10, 6], [9, 6],
        [8, 5], [8, 4], [8, 3], [8, 2], [8, 1], [8, 0],
        [7, 0], [6, 0], [6, 1], [6, 2], [6, 3], [6, 4], [6, 5],
        [5, 6], [4, 6], [3, 6], [2, 6], [1, 6], [0, 6], [0, 7],
        [1, 7], [2, 7], [3, 7], [4, 7], [5, 7], [6, 7]
    ]

    bluePath = [
        [8, 13], [8, 12], [8, 11], [8, 10], [8, 9],
        [9, 8], [10, 8], [11, 8], [12, 8], [13, 8], [14, 8], [14, 7], [14, 6],
        [13, 6], [12, 6], [11, 6], [10, 6], [9, 6],
        [8, 5], [8, 4], [8, 3], [8, 2], [8, 1], [8, 0],
        [7, 0], [6, 0], [6, 1], [6, 2], [6, 3], [6, 4], [6, 5],
        [5, 6], [4, 6], [3, 6], [2, 6], [1, 6], [0, 6], [0, 7],
        [0, 8], [1, 8], [2, 8], [3, 8], [4, 8], [5, 8],
        [6, 9], [6, 10], [6, 11], [6, 12], [6, 13], [6, 14],
        [7, 14], [7, 13], [7, 12], [7, 11], [7, 10], [7, 9], [7, 8]
    ]

    redPath = [
        [13, 6], [12, 6], [11, 6], [10, 6], [9, 6],
        [8, 5], [8, 4], [8, 3], [8, 2], [8, 1], [8, 0],
        [7, 0], [6, 0], [6, 1], [6, 2], [6, 3], [6, 4], [6, 5],
        [5, 6], [4, 6], [3, 6], [2, 6], [1, 6], [0, 6], [0, 7],
        [0, 8], [1, 8], [2, 8], [3, 8], [4, 8], [5, 8],
        [6, 9], [6, 10], [6, 11], [6, 12], [6, 13], [6, 14],
        [7, 14], [8, 14], [8, 13], [8, 12], [8, 11], [8, 10], [8, 9],
        [9, 8], [10, 8], [11, 8], [12, 8], [13, 8], [14, 8], [14, 7],
        [13, 7], [12, 7], [11, 7], [10, 7], [9, 7], [8, 7]
    ]

class countDownThread(threading.Thread):

    def __init__(self, sleep_interval = 30): 
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

    def run(self): 
        print("Spawned new thread in same process.")
        self.stop_timer = False
        while True:
            t = 30
            # If no kill signal is set, sleep for the interval,
            # If kill signal comes in while sleeping, immediately
            #  wake up and handle
            print("Thread is sleeping for ", t , " seconds")
            is_killed = self._kill.wait(self._interval)
            print("Thread is killed value is ", is_killed)
            print("Thread awake")
            if not is_killed :
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
                    updateGameTurn(self.doc_snapshot,self.doc_change, self.db_collection,current_turn,total_players,skip_map, skip_turn)
                    self.server_updated_turn = True

                elif ((self.doc_change is None ) or self.doc_snapshot is None):
                    #The game has started and no one has made a move yet.
                    print("No one made move initially. Skipping turn")
                    if len(skip_map) == 0:
                        for i in range(total_players):
                            if i == current_turn:
                                skip_map.append(1)
                            else : 
                                skip_map.append(0)
                    else:
                        skip_user_index_value = skip_map[current_turn] + 1
                        if skip_user_index_value > 3:
                            if current_turn in skip_turn:
                                pass
                            else:
                                skip_turn.append(current_turn)
                        skip_map[current_turn] = skip_user_index_value

                    current_turn = value['currentTurn']
                    total_players = value['total_players']
                    current_turn +=1
                    currentTurn = current_turn % total_players

                    self.db_collection.update({
                        'currentTurn': currentTurn,
                        'skip_map': skip_map,
                        'skip_turn': skip_turn
                        })  
                    self.server_updated_turn = True
            elif not self.stop_timer :
                print("User performed action within time. Always reset skip turn for user to 0")
                doc_ref = self.db_collection.get()
                value = doc_ref.to_dict()
                skip_map = value['skip_map']
                current_turn = value['currentTurn']
                total_players = value['total_players']
                if len(skip_map) == 0:
                    for i in range(total_players):
                            if i == current_turn:
                                skip_map.append(1)
                            else : 
                                skip_map.append(0)
                else:
                    skip_map[current_turn] = 0
                self.db_collection.update({
                        'skip_map': skip_map
                        })  
                self.server_updated_turn = False

            self.resetTimer()
            if(self.stop_timer == True):
                print("Breaking out of while loop. Thread can end peacefully.")
                break

    # Stop timer stops the timer but does not end while loop in run() method. It just awakes the thread if it is sleeping. Usefull for updating 
    # user turns
    def stopTimer(self):
        if(self.server_updated_turn):
            return
        self._kill.set()

    # End timer kill the thread. Signifies the game is over
    def endTimer(self):
        if self.doc_watcher != None :
            print("Ending timer")
            self.doc_watcher.unsubscribe()
            self.stop_timer = True
            self._kill.set()

    def updateGameState(self, doc_snapshot,doc_changes):
        self.doc_snapshot = doc_snapshot
        self.doc_change = doc_changes

    def resetTimer(self):
        if self._kill.is_set() :
                self.is_killed = False
                self._kill.clear()

    def initDocumentWatcher(self, roomType, roomId, gameMode):
        #Start watching the document for updates
        self.roomType = roomType
        self.roomId = roomId
        self.gameMode = gameMode
        
        db_collection = db.collection('ludo').document(roomType).collection(f'{gameMode}_games').document(roomId)
        self.doc_watcher = db_collection.on_snapshot(on_snapshot)
        self.db_collection = db_collection
    

timerThread = countDownThread(sleep_interval=30)


def updateGameTurn(doc_snapshot,doc_change, db_collection, current_turn, total_players, skip_map, skip_turn):
    skip_user_index_value = skip_map[current_turn] + 1
    if skip_user_index_value > 3:
        if current_turn in skip_turn:
            pass
        else:
            skip_turn.append(current_turn)
    skip_map[current_turn] = skip_user_index_value

    currentUserTurn = current_turn
    currentUserTurn +=1
    currentTurn = currentUserTurn % total_players
    mapping = {
        'currentTurn': currentTurn,
        'skip_map': skip_map,
        'skip_turn': skip_turn
                }
    print("Updated turn")
    db_collection.update(mapping)
    return

def on_snapshot(doc_snapshot, doc_changes, read_time):
    for change in doc_changes:
        if change.type.name == 'MODIFIED':
            print('Document snapshot', doc_snapshot[0].to_dict)
            timerThread.stopTimer()
            timerThread.updateGameState(doc_snapshot,change)


class Token:
    def __init__(self, token_type, position, token_state, index, value):
        self.token_type = token_type
        self.position = position
        self.token_state = token_state
        self.index = index
        self.value = value

def updateBoardState(token, destination, path_position):
    cut_token = None

    if destination in game_state.star_positions:
        game_state.game_tokens[token.index].token_state = TokenState.safe
        return None

    tokens_at_destination = [tkn for tkn in game_state.game_tokens if tkn.position == destination]

    if not tokens_at_destination:
        game_state.game_tokens[token.index].token_state = TokenState.normal
        return None

    tokens_same_type = [tkn for tkn in tokens_at_destination if tkn.token_type == token.token_type]

    if len(tokens_same_type) == len(tokens_at_destination):
        for tkn in tokens_same_type:
            game_state.game_tokens[tkn.index].token_state = TokenState.safe_in_pair
        game_state.game_tokens[token.index].token_state = TokenState.safe_in_pair
        return None

    if len(tokens_same_type) < len(tokens_at_destination):
        for tkn in tokens_at_destination:
            if tkn.token_type != token.token_type and game_state.game_tokens[tkn.index].token_state != TokenState.safe_in_pair:
                cut_token = game_state.game_tokens[tkn.index]
            elif tkn.token_type == token.token_type:
                game_state.game_tokens[tkn.index].token_state = TokenState.safe_in_pair

        game_state.game_tokens[token.index].token_state = TokenState.safe_in_pair if tokens_same_type else TokenState.normal

        return cut_token

    return None


def updateInitialPositions(token):
    if token.token_type == "green":
        game_state.green_initial.append(token.position)
    elif token.token_type == "yellow":
        game_state.yellow_initial.append(token.position)
    elif token.token_type == "blue":
        game_state.blue_initial.append(token.position)
    elif token.token_type == "red":
        game_state.red_initial.append(token.position)


def cutToken(token):
    token_id = token.index

    if token.token_type == "green":
        game_state.game_tokens[token_id].token_state = TokenState.initial
        game_state.game_tokens[token_id].position = game_state.green_initial[0]
        game_state.green_initial.pop(0)
    elif token.token_type == "yellow":
        game_state.game_tokens[token_id].token_state = TokenState.initial
        game_state.game_tokens[token_id].position = game_state.yellow_initial[0]
        game_state.yellow_initial.pop(0)
    elif token.token_type == "blue":
        game_state.game_tokens[token_id].token_state = TokenState.initial
        game_state.game_tokens[token_id].position = game_state.blue_initial[0]
        game_state.blue_initial.pop(0)
    elif token.token_type == "red":
        game_state.game_tokens[token_id].token_state = TokenState.initial
        game_state.game_tokens[token_id].position = game_state.red_initial[0]
        game_state.red_initial.pop(0)


class Position:
    def __init__(self, row, col):
        self.row = row
        self.col = col

class TokenState:
    initial = "initial"
    home = "home"
    normal = "normal"
    safe = "safe"
    safeinpair = "safeinpair"

class GameState:
    def __init__(self):
        self.game_tokens = [
            # Green Token
            Token("green", Position(2, 2), TokenState.initial, 0, 0),
            Token("green", Position(2, 3), TokenState.initial, 1, 0),
            Token("green", Position(3, 2), TokenState.initial, 2, 0),
            Token("green", Position(3, 3), TokenState.initial, 3, 0),
            # Yellow Token
            Token("yellow", Position(2, 11), TokenState.initial, 4, 0),
            Token("yellow", Position(2, 12), TokenState.initial, 5, 0),
            Token("yellow", Position(3, 11), TokenState.initial, 6, 0),
            Token("yellow", Position(3, 12), TokenState.initial, 7, 0),
            # Blue Token
            Token("blue", Position(11, 11), TokenState.initial, 8, 0),
            Token("blue", Position(11, 12), TokenState.initial, 9, 0),
            Token("blue", Position(12, 11), TokenState.initial, 10, 0),
            Token("blue", Position(12, 12), TokenState.initial, 11, 0),
            # Red Token
            Token("red", Position(11, 2), TokenState.initial, 12, 0),
            Token("red", Position(11, 3), TokenState.initial, 13, 0),
            Token("red", Position(12, 2), TokenState.initial, 14, 0),
            Token("red", Position(12, 3), TokenState.initial, 15, 0),
        ]
        self.star_positions = [
            Position(6, 1),
            Position(2, 6),
            Position(1, 8),
            Position(6, 12),
            Position(8, 13),
            Position(12, 8),
            Position(13, 6),
            Position(8, 2)
        ]
        self.green_initial = []
        self.yellow_initial = []
        self.blue_initial = []
        self.red_initial = []

    def getPosition(self,token_type, step):
        destination = None
        path = None

        if token_type == "green":
            path = Path.greenPath
        elif token_type == "yellow":
            path = Path.yellowPath
        elif token_type == "blue":
            path = Path.bluePath
        elif token_type == "red":
            path = Path.redPath

        if path is not None and 0 <= step < len(path):
            node = path[step]
            destination = Position(node[0], node[1])

        return destination
    
    def getPositionByCoordinates(self, token_type, row, col):
        path = None

        if token_type == "green":
            path = Path.greenPath
        elif token_type == "yellow":
            path = Path.yellowPath
        elif token_type == "blue":
            path = Path.bluePath
        elif token_type == "red":
            path = Path.redPath

        index = path.index([row,col])
        return index

    def moveToken(self,token, steps):
        destination = None
        path_position = None

        if token.token_state == TokenState.home:
            return

        if token.token_state == TokenState.initial and steps != 6:
            return

        if token.token_state == TokenState.initial and steps == 6:
            destination = self.getPosition(token_type = token.token_type, step= 0)
            path_position = 0
            updateInitialPositions(token)
            cut_token = updateBoardState(token, destination, path_position)
            game_state.game_tokens[token.index].position = destination
            game_state.game_tokens[token.index].position_in_path = path_position
            # game_state.notify_listeners()
            
        elif token.token_state != TokenState.initial:
            step = token.position_in_path + steps
            if step > 56:
                return
            destination = self.getPosition(token_type = token.token_type, step= step)
            path_position = step
            cut_token = updateBoardState(token, destination, path_position)
            duration = 0
            for i in range(1, steps + 1):
                 duration += 500
                 game_state.move_token_step(token=token, step=i)
                #TODO investigate how this will affect code
                # future = Future.delayed(Duration(milliseconds=duration), lambda i=i: move_token_step(token, i))

            if cut_token is not None:
                cut_steps = cut_token.position_in_path
                for i in range(1, cut_steps + 1):
                    duration += 100
                    game_state.move_cut_token_step(cut_token=cut_token, step=i)
                    #TODO investigate how this will affect code
                    # future2 = Future.delayed(Duration(milliseconds=duration), lambda i=i: move_cut_token_step(cut_token, i))

                # future2 = Future.delayed(Duration(milliseconds=duration), lambda: cut_token_and_notify(cut_token))

    def move_token_step(self,token, step):
        step_loc = token.position_in_path + 1
        game_state.game_tokens[token.index].position = self.getPosition(token_type = token.token_type, step= step_loc)
        game_state.game_tokens[token.index].position_in_path = step_loc
        token.position_in_path = step_loc
        #TODO investigate how this will affect code
        # notify_listeners()

    def move_cut_token_step(self,cut_token, step):
        step_loc = cut_token.position_in_path - 1
        game_state.game_tokens[cut_token.index].position = self.getPosition(token_type = cut_token.token_type, step= step_loc)
        game_state.game_tokens[cut_token.index].position_in_path = step_loc
        cut_token.position_in_path = step_loc
        #TODO investigate how this will affect code
        # notify_listeners()

    def cut_token_and_notify(cut_token):
        cut_token(cut_token)
        #TODO investigate how this will affect code
        # notify_listeners()

    def cut_token(token):
        token_id = token.index

        if token.token_type == "green":
            game_state.game_tokens[token_id].token_state = TokenState.initial
            game_state.game_tokens[token_id].position = game_state.green_initial[0]
            game_state.green_initial.pop(0)
        elif token.token_type == "yellow":
            game_state.game_tokens[token_id].token_state = TokenState.initial
            game_state.game_tokens[token_id].position = game_state.yellow_initial[0]
            game_state.yellow_initial.pop(0)
        elif token.token_type == "blue":
            game_state.game_tokens[token_id].token_state = TokenState.initial
            game_state.game_tokens[token_id].position = game_state.blue_initial[0]
            game_state.blue_initial.pop(0)
        elif token.token_type == "red":
            game_state.game_tokens[token_id].token_state = TokenState.initial
            game_state.game_tokens[token_id].position = game_state.red_initial[0]
            game_state.red_initial.pop(0)



# Create an instance of GameState
game_state = GameState()
two_player_colors = {
            "green": "blue",
            "blue": "green",
            "red": "yellow",
            "yellow": "red",
        }

@ludoapp.route("/")
def home():
    return 'Server is running'

@ludoapp.route("/startLudoGame/", methods = ["POST"])
async def ludoRoom():
    data = request.json
    userId = data["userId"]
    gameMode = data["gameMode"] # cash free private
    roomType = data["roomType"] # two four oneToWin
    roomSize = data["roomSize"] # 2 or 4
#    roomSize = 1
    cash = data.get('cash', None)
    generateCode = data.get("generateCode", False)

    roomId, color = await createLudoRoom(userId, gameMode, roomType, roomSize, cash, generateCode)
    
    return jsonify({
        "roomId": roomId,
        "colors": color,
    })

async def createLudoRoom(userId: str, gameMode: str, roomType: str, roomSize: int, cash: int, generateCode:bool) -> tuple:
    db_collection = db.collection('ludo').document(roomType).collection(f'{gameMode}_games')

    if (cash == None):
        query = None
        if (not generateCode):
            query = db_collection.where('total_players', '==', roomSize).where('current_number', '<', roomSize).get()
    else:
        fundStatus = consumeCash(userId, cash)
        if (fundStatus):
            query = db_collection.where('total_players', '==', roomSize).where('current_number', '<', roomSize).where('cash', '==', cash).get()
        else:
            return (220)
        
    first_id = None

    if (query != None):

        for doc in query:
            document = doc.to_dict()
            first_id = doc.id

            taken_colors = set(document['taken_colors'])
            available_colors = colors - taken_colors
            print(available_colors)
            if (roomSize != 2):
                chosen_colors = random.sample(list(available_colors), 1)
            else:
                chosen_colors = [two_player_colors[list(taken_colors)[0]]]

            color_map = document['color_map']

            for color in chosen_colors:
                color_map[color] = userId
            
            db_collection.document(first_id).update({
                "current_number": firestore.Increment(1),
                "players": firestore.ArrayUnion([userId]),
                "taken_colors": firestore.ArrayUnion(chosen_colors),
                "color_map": color_map,
            })

            if((document["current_number"] + 1) == document["total_players"]):
                # Last person for the lobby joined. Start game timer
                timerThread.initDocumentWatcher(roomType= roomType, roomId=first_id, gameMode= gameMode)
                # if(not timerThread.is_alive()):
                #     timerThread = None
                    # timerThread = countDownThread(sleep_interval=30)
                # timerThread.start()
                pass

            return (first_id, chosen_colors)
    
    chosen_colors = random.sample(list(colors), 1)

    data_map = {
        'total_players': roomSize, 
        'current_number': 1, 
        'skip_turn': [],
        'skip_map': [], 
        'players': [userId], 
        'currentTurn': random.randint(0, roomSize-1), 
        'gameMode': gameMode,
        'taken_colors': chosen_colors,
        'color_map': {k: userId for k in chosen_colors},
        }
    
    if (generateCode):
        data_map['code'] = generateAlphaNumeric(8)    

    if (cash != None):
        data_map['cash'] = cash


    doc_ref = db_collection.add(data_map)
    first_id = doc_ref[-1].id

    await createPawns(gameMode, roomType, first_id)
    
    return (first_id, chosen_colors)

def set_pawn_position(pawn_collection, pawn_id):
    pawn_collection.document(str(pawn_id)).set({
        "positionInPath": -1
    })

async def createPawns(gameMode: str, roomType: str, roomId: str):
    pawn_collection = db.collection('ludo').document(f'{roomType}').collection(f'{gameMode}_games').document(roomId).collection('pawns')

    threads = []
    for i in range(0, 16):
        thread = threading.Thread(target=set_pawn_position, args=(pawn_collection, i))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()



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

@ludoapp.route('/joinLudoWithCode/', methods = ["POST"])
def joinWithCode():
    data = request.json
    userId = data.get('userId', '')
    roomType = data.get('roomType', '')
    gameMode = data.get('gameMode', '')
    code = data.get('code', '')

    db_collection = db.collection('ludo').document(f'{roomType}').collection(f'{gameMode}_games')
    query = db_collection.where('code', '==', code).get()
    for doc in query:
        document = doc.to_dict()
        first_id = doc.id

        taken_colors = set(document['taken_colors'])
        available_colors = colors - taken_colors
        roomSize = doc['total_players']
        if (roomSize != 2): 
            chosen_colors = random.sample(list(available_colors), 1)
        else:
            chosen_colors = [two_player_colors[list(taken_colors)[0]]]

        color_map = document['color_map']

        for color in chosen_colors:
            color_map[color] = userId
        
        db_collection.document(first_id).update({
            "current_number": firestore.Increment(1),
            "players": firestore.ArrayUnion([userId]),
            "taken_colors": firestore.ArrayUnion(chosen_colors),
            "color_map": color_map,
        })

        #TODO: Store pawn positions in a separate collection

        return jsonify({
        "roomId": first_id,
        "colors": color,
    })
    
    return jsonify({"error": 230,})



def generateAlphaNumeric(length):
    characters = string.ascii_letters + string.digits

    # Generate the random alphanumeric string
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string


@ludoapp.route('/movePawn/', methods = ["POST"])
def movePawn():
    #Fetch data from request
    data = request.json
    userId = data.get('userId', '')
    roomId = data.get('roomId', '')
    gameMode = data.get('gameMode', '')
    roomType = data.get('roomType', '')
    pawnId = data.get('id','')

    db_collection = db.collection('ludo').document(roomType).collection(gameMode+"_games")
    value = db_collection.document(roomId).get()
    value = value.to_dict()

    die_roll_value = value['roll']
    totalPlayers = value['total_players']
    currentTurn = value['currentTurn']
    colorMap = value['color_map']

    token = None 
    for tkn in game_state.game_tokens:
        if tkn.index == pawnId:
            token = tkn


    print("Die roll value is", die_roll_value)
    print("Pawn id is ", pawnId)

    print("Token color is ", token.token_type)
    print("Token row value is ", token.position.row)
    print("Token col value is ", token.position.col)
    game_state.moveToken(token= token, steps= die_roll_value)

    print("Token color post move is ", token.token_type)
    print("Token row value post move is ", token.position.row)
    print("Token col value post move is ", token.position.col)

    row = token.position.row
    col = token.position.col

    path_data = None
    try:
        path_data = game_state.getPositionByCoordinates(token.token_type,row,col)
    except:
        print("User tried to move a pawn whos die roll value is not 6 and pawn is at initial state. Do nothing")
        return jsonify({205:'OK'})
    print("path data", path_data)
    print("path data + roll value", path_data + die_roll_value)
    if(path_data + die_roll_value < 56):
        if(die_roll_value == 6 and token.token_state == TokenState.initial):
            print("Initial state and die roll 6")
            db_collection.document(roomId).collection("pawns").document(str(pawnId)).update({
            'positionInPath': 0
        })
        elif (die_roll_value != 6 and token.token_state != TokenState.initial):
            print("Non Initial state and die roll not 6")
            db_collection.document(roomId).collection("pawns").document(str(pawnId)).update({
            'positionInPath': firestore.Increment(die_roll_value),
            })
            currentTurn = currentTurn + 1
            currentTurn = currentTurn % totalPlayers
            db_collection.document(roomId).update({
                'currentTurn': currentTurn
            })
        elif (die_roll_value != 6 and token.token_state == TokenState.initial):
            print("Initial state and die roll not 6")
            currentTurn = currentTurn + 1
            currentTurn = currentTurn % totalPlayers
            db_collection.document(roomId).update({
                'currentTurn': currentTurn
            })
        else:
            print("Non Initial state and die roll 6")
            db_collection.document(roomId).collection("pawns").document(str(pawnId)).update({
            'positionInPath': path_data
            })
    elif(path_data + die_roll_value == 56):
        token.token_state = TokenState.home
        db_collection.document(roomId).collection("pawns").document(str(pawnId)).update({
            'positionInPath': 56
        })
            
    #Check for win state
    colorMapKey = list(colorMap.keys())
    colorMapVal = list(colorMap.values())
    tokenColor = colorMapKey[colorMapVal.index(userId)]
   
    winState = False
    if gameMode == 'one_to_win':
        
        for token in game_state.game_tokens:
            # Check for token color
            if(tokenColor == token.token_type):
                if(token.token_state == TokenState.home):
                    winState = True

            if winState :
                break
        
    else:
        winState = True

        for token in game_state.game_tokens:
            # Check for token color
            if(tokenColor == token.token_type):
                if(token.token_state != TokenState.home):
                    winState = False
        
            if not winState:
                break

    if winState:
        timerThread.endTimer()
        db_collection.document(roomId).update({
            'winner': userId
        })

    return jsonify({200:'OK'})

@ludoapp.route('/rollDice/', methods = ["POST"])
def rollDice():

    #Fetch data from request
    data = request.json
    userId = data.get('userId', '')
    roomId = data.get('roomId', '')
    gameMode = data.get('gameMode', '')
    roomType = data.get('roomType', '')
    print('room type ', gameMode)
    # positionInPath = data.get('positionInPath','')

    #Fetch relevant document from firestore
    db_collection = db.collection('ludo').document(f'{roomType}').collection(f'{gameMode}_games')
    value = db_collection.document(roomId).get()
    value = value.to_dict()
    color_map = value['color_map']
    totalPlayers = value['total_players']
    
    currentTurn = int(value.get('currentTurn'))
    #Generate a random number
    die_roll_value = random.randint(1,6)
    # die_roll_value = 6

    print('Game state data ', game_state.star_positions)

    tokenColor = None
    for color,user in color_map.items():
        if user == userId:
            tokenColor = color

    if(tokenColor == None):
        return jsonify({"Invalid token color. Did someone tamper the code from client end? Internal Server Error": 500,})

    #initial state when game starts
    if(die_roll_value == 6 and pawnAtStartingPosition(tokenColor)):
        print("All pawns are at starting position and die roll 6")
        db_collection.document(roomId).update({
        'roll': die_roll_value

        })
        
        
    elif (die_roll_value != 6 and pawnAtStartingPosition(tokenColor)) :
        print("All pawns are at starting position and die roll not 6")
        currentTurn = currentTurn + 1
        currentTurn = currentTurn % int(totalPlayers)
        db_collection.document(roomId).update({
        'roll': die_roll_value,
        'currentTurn': currentTurn
        })
    elif (die_roll_value == 6 and not pawnAtStartingPosition(tokenColor)):
        print("All pawns are not at starting position and die roll 6")
        db_collection.document(roomId).update({
        'roll': die_roll_value,
        })

    else :
        print("All pawns are not at starting position and die roll not 6")
        db_collection.document(roomId).update({
        'roll': die_roll_value,
        })

    return jsonify({'roll':die_roll_value})

def pawnAtStartingPosition(tokenColors):
    print("pawnAtStartingPosition Method: ", tokenColors)
    for token in game_state.game_tokens:
        # Check for token color
        if(tokenColors == token.token_type):
            if(token.token_state != TokenState.initial):
                return False
    return True

async def createPawns(gameMode: str, roomType: str, roomId: str):
    pawn_collection = db.collection('ludo').document(f'{roomType}').collection(f'{gameMode}_games').document(roomId).collection('pawns')

    tasks = []
    for i in range(0, 16):
        # Append coroutine without awaiting
        task = pawn_collection.document(str(i)).set({
            "positionInPath": -1
        })
        tasks.append(task)

    # Await all tasks together
    # await asyncio.gather(*tasks)

if __name__ == '__main__':
    ludoapp.debug = True
    ludoapp.run() 
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    ludoapp.logger.handlers = gunicorn_logger.handlers
    ludoapp.logger.setLevel(gunicorn_logger.level)



'''
    rollDie -> Inputs: userId, Output: (int) 1-6    (Keep track of die roll in firebase)
                                                    (if all of users pawns are at home and number isn't 6, go to next person automatically)

    movePawn -> Inputs: userId, token_id            (Use die roll number on firebase to move the given token id by the amount)

    in movePawn also consider winningStates and game end state
    write a function for game end state which updates the "winner" field and handles cash if required

    structure of a pawn on firebase:
        {
      "id": id,
      "type": green, yellow, ....,
      "positionRow": tokenPosition.props, [row_idx, col_idx]
      "state": tokenState.toString().split('.').last, -> (initial, home, normal, safe, safeinpair)
      "positionInPath": positionInPath,
    };
'''
