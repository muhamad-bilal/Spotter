import { useState } from 'react'

import { postTrip } from './api/client.js'
import Placeholder from './components/Placeholder/Placeholder.jsx'
import RouteMap from './components/RouteMap/RouteMap.jsx'
import TripForm from './components/TripForm/TripForm.jsx'
import TripSummary from './components/TripSummary/TripSummary.jsx'
import './App.css'

export default function App() {
  // React state only -- nothing is persisted to the browser.
  const [result, setResult] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [serverError, setServerError] = useState(null)

  const handleSubmit = async (values) => {
    setIsLoading(true)
    setServerError(null)
    try {
      setResult(await postTrip(values))
    } catch (error) {
      setServerError(error.message)
      setResult(null)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-inner">
          <h1 className="app__title">
            <span className="app__mark" aria-hidden="true" />
            ELD Trip Planner
          </h1>
          <p className="app__subtitle">
            Hours-of-service routing and daily log sheets · property carrier,
            70&nbsp;hr / 8&nbsp;day
          </p>
        </div>
      </header>

      <main className="app__main">
        <TripForm
          onSubmit={handleSubmit}
          isLoading={isLoading}
          serverError={serverError}
        />

        <div className="app__results">
          {result ? (
            <>
              <TripSummary trip={result.trip} />
              <RouteMap route={result.route} />
              <Placeholder
                title="Daily log sheets"
                phase="logs"
                lines={4}
                description={`${result.logs.length} duty-status ${
                  result.logs.length === 1 ? 'grid' : 'grids'
                } will be drawn here, one per calendar day.`}
              />
            </>
          ) : (
            <section className="card empty">
              <div className="empty__inner">
                <span className="empty__mark" aria-hidden="true" />
                <h2 className="empty__title">No trip planned yet</h2>
                <p className="empty__text">
                  Enter the current location, pickup and dropoff, plus the hours
                  already used in the 8-day cycle. The planner works out a compliant
                  driving schedule and the daily logs that go with it.
                </p>
              </div>
            </section>
          )}
        </div>
      </main>

      <footer className="app__footer">
        Drive time assumes a constant 55&nbsp;mph. Fuel stop every 1,000&nbsp;miles;
        1&nbsp;hour on duty at pickup and at dropoff.
      </footer>
    </div>
  )
}
