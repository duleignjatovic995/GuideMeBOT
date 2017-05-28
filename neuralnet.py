from math import tanh as sigmoid
import sqlite3.dbapi2 as sqlite

def d_tanh(y):
    """
    Calculates the derivative of tanh function.

    :param y: Hyperbolic tang function
    :return: Derivative of tanh
    """
    return 1.0 - y * y


# One object per query
class SearchNet:
    def __init__(self, dbname):
        self.conn = sqlite.connect(dbname)

    def __del__(self):
        self.conn.close()

    def make_tables(self):
        # Table used for checking existing word query combinations
        self.conn.execute('CREATE TABLE hiddennode(create_key)')
        # Input to hidden weights
        self.conn.execute('CREATE TABLE wordhidden(fromid, toid, strength)')
        # Hidden to output weights
        self.conn.execute('CREATE TABLE hiddenurl(fromid, toid, strength)')
        self.conn.commit()

    def get_strength(self, fromid, toid, layer):
        """
        Returns weight between two nodes.

        :param fromid: Relative input node id
        :param toid: Relative output node id
        :param layer: Layer in feedforward net
        """
        if layer == 0:
            table = 'wordhidden'
        else:
            table = 'hiddenurl'
        # Get weight from proper table
        cursor = self.conn.execute(
            'SELECT strength FROM %s WHERE fromid = %d AND toid = %d' % (table, fromid, toid)
        )
        result = cursor.fetchone()
        if result is None:
            if layer == 0:
                # Word to hidden default negative for additional new words - layer 0
                return - 0.2
            if layer == 1:
                return 0
        return result[0]

    def set_strength(self, fromid, toid, layer, strength):
        """
        Check if connection already exists and update or create
        connection with a new strength.

        :param fromid: Relative input node id 
        :param toid: Relative output node id
        :param layer: Layer in feedforward net
        :param strength: Weight in connection
        """
        if layer == 0:
            table = 'wordhidden'
        else:
            table = 'hiddenurl'
        cursor = self.conn.execute(
            'SELECT rowid FROM %s WHERE fromid = %d AND toid = %d' % (table, fromid, toid)
        )
        result = cursor.fetchone()
        if result is None:
            self.conn.execute(
                'INSERT INTO %s (fromid, toid, strength) VALUES (%d, %d, %f)' % (table, fromid, toid, strength)
            )
        else:
            rowid = result[0]
            self.conn.execute(
                'UPDATE %s SET strength = %f WHERE rowid = %d' % (table, strength, rowid)
            )

    def generate_hidden_node(self, wordids, urls):
        """
        Creates new node in the hidden layer every time it gets
        new combination of words.

        :param wordids: word id's from query
        :param urls: 
        """
        if len(wordids) > 3:
            wordids = wordids[:3]
        # Check if we alredy created a node for this set of words
        create_key = '_'.join(sorted([str(wi) for wi in wordids]))
        cursor = self.conn.execute(
            "SELECT rowid FROM hiddennode WHERE create_key = '%s'" % create_key
        )
        result = cursor.fetchone()

        # If not -> create it
        if result is None:
            cursor1 = self.conn.execute(
                "INSERT INTO hiddennode (create_key) VALUES ('%s')" % create_key
            )
            hiddenid = cursor1.lastrowid
            # Put in default weights
            for wordid in wordids:
                self.set_strength(wordid, hiddenid, 0, 1.0 / len(wordids))

            for urlid in urls:
                self.set_strength(hiddenid, urlid, 1, 0.1)
            self.conn.commit()

    def get_all_hidden_ids(self, wordids, urlids):
        """
        Finds all nodes from hidden layer relevant to a
        specific query.

        :param wordids: word id's from query
        :param urlids: 
        :return: hidden nodes
        """
        l1 = {}
        for wordid in wordids:
            # Get all hidden nodes connected to a specific word
            cursor = self.conn.execute(
                'SELECT toid FROM wordhidden WHERE fromid = %d' % wordid
            )
            for row in cursor:
                l1[row[0]] = 1
        for urlid in urlids:
            # Get all hidden nodes conected to specific urls
            cursor = self.conn.execute(
                'SELECT fromid FROM hiddenurl WHERE toid = %d' % urlid
            )
            for row in cursor:
                l1[row[0]] = 1
        return l1.keys()

    def setup_network(self, wordids, urlids):
        """
        Setup neural net for specific query

        :param wordids: word id's from query
        :param urlids: 
        """
        # Value list
        self.wordids = wordids
        self.hidden_ids = self.get_all_hidden_ids(wordids, urlids)
        self.urlids = urlids

        # Node outputs
        self.ai = [1.0] * len(self.wordids)
        self.ah = [1.0] * len(self.hidden_ids)
        self.ao = [1.0] * len(self.urlids)

        # Create weight matrix for specific query
        self.wi = [
            [
                self.get_strength(wordid, hiddenid, 0) for hiddenid in self.hidden_ids
            ] for wordid in self.wordids
        ]

        self.wo = [
            [
                self.get_strength(hiddenid, urlid, 1) for urlid in self.urlids
            ] for hiddenid in self.hidden_ids
        ]

    def feedforward(self):
        """
        Feedforward trough neural net.

        :return: Output nodes values
        """
        # The only inputs are the query words
        for i in range(len(self.wordids)):
            self.ai[i] = 1.0
        # Hidden activations
        for j in range(len(self.hidden_ids)):
            sum = 0.0
            for i in range(len(self.wordids)):
                sum += self.ai[i] * self.wi[i][j]
            self.ah[j] = sigmoid(sum)

        # Output activations
        for k in range(len(self.urlids)):
            sum = 0.0
            for j in range(len(self.hidden_ids)):
                sum += self.ah[j] * self.wo[j][k]
            self.ao[k] = sigmoid(sum)
        return self.ao[:]

    def get_result(self, wordids, urlids):
        """
        Get result for a specific query based on a neural
        net.

        :param wordids: word id's from query
        :param urlids: 
        :return: Output nodes values
        """
        self.setup_network(wordids, urlids)
        return self.feedforward()

    def backpropagate(self, targets, alpha=0.5):
        """
        Back propagate once trough neural net.

        :param targets: Desired output values
        :param alpha: Learning rate (default=0.5)
        """
        # Calculate errors of output nodes
        output_deltas = [0.0] * len(self.urlids)
        for k in range(len(self.urlids)):
            error = targets[k] - self.ao[k]
            output_deltas[k] = d_tanh(self.ao[k]) * error

        # Calculate errors for hidden layer
        hidden_detltas = [0.0] * len(self.hidden_ids)
        for j in range(len(self.hidden_ids)):
            error = 0.0
            for k in range(len(self.urlids)):
                error += output_deltas[k] * self.wo[j][k]
            hidden_detltas[j] = d_tanh(self.ah[j]) * error

        # Update output weights
        for j in range(len(self.hidden_ids)):
            for k in range(len(self.urlids)):
                change = output_deltas[k] * self.ah[j]
                self.wo[j][k] += alpha * change

        # Update input weights
        for i in range(len(self.wordids)):
            for j in range(len(self.hidden_ids)):
                change = hidden_detltas[j] * self.ai[i]
                self.wi[i][j] += alpha * change

    def train_query(self, wordids, urlids, selectedurl):
        """
        Trains neural net based on user clicks and updates database.

        :param wordids: word id's from query
        :param urlids: relevant url id's
        :param selectedurl: selected url
        """
        # generate a hidden node if necessary
        self.generate_hidden_node(wordids, urlids)

        self.setup_network(wordids, urlids)
        self.feedforward()
        # Set desired values
        targets = [0.0] * len(urlids)
        targets[urlids.index(selectedurl)] = 1.0
        self.backpropagate(targets)
        self.update_db()

    def update_db(self):
        """
        Update newly calculated weights to database.
        """
        # Set them to database values
        for i in range(len(self.wordids)):
            for j in range(len(self.hidden_ids)):
                self.set_strength(self.wordids[i], self.hidden_ids[j], 0, self.wi[i][j])
        for j in range(len(self.hidden_ids)):
            for k in range(len(self.urlids)):
                self.set_strength(self.hidden_ids[j], self.urlids[k], 1, self.wo[j][k])
        self.conn.commit()


if __name__ == "__main__":
    srch = SearchNet('nn.db')
    srch.make_tables()
