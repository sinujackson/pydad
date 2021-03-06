import logging
from time import *

import findspark
import pyspark.sql.functions as F
from pyspark import SparkContext
from pyspark.mllib.evaluation import BinaryClassificationMetrics
from pyspark.mllib.linalg import Vectors
from pyspark.mllib.regression import LabeledPoint
from pyspark.mllib.tree import RandomForest
from pyspark.sql import SQLContext
# This is not recognized by IntelliJ!, but still works.
from pyspark.sql.functions import col

from src.pydad import __version__
from src.pydad.conf import ConfigParams


def main():
    _logger = logging.getLogger(__name__)
    findspark.init(ConfigParams.__SPARK_HOME__)
    SparkContext.setSystemProperty('spark.executor.memory', '48g')
    SparkContext.setSystemProperty('spark.driver.memory', '6g')

    sc = SparkContext(appName='SparkTest', master=ConfigParams.__MASTER_UI__)
    sqlContext = SQLContext(sc)

    df = sqlContext.read.csv(
        ConfigParams.__DAD_PATH__, header=True, mode="DROPMALFORMED"
    )

    # CHANGE THIS for model refinement
    # tlos = df.select(df.columns[154:155]) # For reference only
    # morbidity = df.select(df.columns[161:]) # For reference only
    # df.select([c for c in df.columns if c in ['TLOS_CAT', 'COLNAME', 'COLNAME']]).show()
    # transformed_df = df.rdd.map(lambda row: LabeledPoint(row[0], Vectors.dense(row[1:-1])))

    RANDOM_SEED = 13579
    TRAINING_DATA_RATIO = 0.7
    RF_NUM_TREES = 3
    RF_MAX_DEPTH = 4
    RF_MAX_BINS = 12

    # String type converted to float type.
    df = df.select(*(col(c).cast("float").alias(c) for c in df.columns))

    # Change all NA to 0
    df = df.na.fill(0)

    # This needs to be CHANGED AS ABOVE.
    # row[7:-1] 7 here is 161 - 154 (154 is TLOS and 161 is the index of morbidities devived variables)
    transformed_df = df.select(df.columns[154:]).rdd.map(lambda row: LabeledPoint(row[0], Vectors.dense(row[7:-1])))

    print(transformed_df.take(5))

    splits = [TRAINING_DATA_RATIO, 1.0 - TRAINING_DATA_RATIO]
    training_data, test_data = transformed_df.randomSplit(splits, RANDOM_SEED)

    print("Number of training set rows: %d" % training_data.count())
    print("Number of test set rows: %d" % test_data.count())

    start_time = time()

    # categoricalFeaturesInfo={} means continuous variables. This needs to be changed too.
    # in pyspark you would need a syntax like this n:m , where n is the column,
    # and m is the number of categories minus 1,
    # and you can have multiple columns with categorical variables
    # each seperated with a comma.
    # Spark use MaxBins to specify a feature is categorical or continuous.
    # If the number of distinct values <= MaxBins, it is categorical.
    # TLOS MAX = 10 with 6 distinct classes
    model = RandomForest.trainClassifier(training_data, numClasses=11,
                                         categoricalFeaturesInfo={},
                                         numTrees=RF_NUM_TREES, featureSubsetStrategy="auto", impurity="gini",
                                         maxDepth=RF_MAX_DEPTH, maxBins=RF_MAX_BINS, seed=RANDOM_SEED)

    end_time = time()
    elapsed_time = end_time - start_time
    print("Time to train model: %.3f seconds" % elapsed_time)

    predictions = model.predict(test_data.map(lambda x: x.features))
    labels_and_predictions = test_data.map(lambda x: x.label).zip(predictions)
    acc = labels_and_predictions.filter(lambda x: x[0] == x[1]).count() / float(test_data.count())
    print("Model accuracy: %.3f%%" % (acc * 100))

    start_time = time()

    metrics = BinaryClassificationMetrics(labels_and_predictions)
    print("Area under Precision/Recall (PR) curve: %.f" % (metrics.areaUnderPR * 100))
    print("Area under Receiver Operating Characteristic (ROC) curve: %.3f" % (metrics.areaUnderROC * 100))

    end_time = time()
    elapsed_time = end_time - start_time
    print("Time to evaluate model: %.3f seconds" % elapsed_time)

    # Save model
    model.save(sc, "scratch/pydad/pythonRFModel")

    _logger.info("Script ends here")
    print(__version__)


def myConcat(*cols):
    return F.concat(*[F.coalesce(c, F.lit("*")) for c in cols])


if __name__ == '__main__':  # if we're running file directly and not importing it
    main()  # run the main function
