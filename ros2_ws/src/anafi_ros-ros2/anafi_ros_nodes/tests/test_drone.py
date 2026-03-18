
import unittest

if __name__ == '__main__':

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()


    suite.addTests(loader.loadTestsFromName('test_drone_connection'))
    suite.addTests(loader.loadTestsFromName('test_drone_camera'))
    suite.addTests(loader.loadTestsFromName('test_drone_gimbal'))
    suite.addTests(loader.loadTestsFromName('test_drone_topic'))
    suite.addTests(loader.loadTestsFromName('test_drone_move'))
    suite.addTests(loader.loadTestsFromName('test_drone_home'))
    suite.addTests(loader.loadTestsFromName('test_drone_followme'))
    suite.addTests(loader.loadTestsFromName('test_drone_POI'))


    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    

    if result.wasSuccessful():
        exit(0)
    else:
        exit(1)
